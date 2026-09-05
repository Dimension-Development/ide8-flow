import base64
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI
from fastapi.testclient import TestClient
import identity_media
import pdf_extraction as extraction
from store import DocStore
from workspace import WorkspaceConflict,design_markdown


class InlineThread:
    def __init__(self,target,args,**kwargs):
        self.target,self.args=target,args
    def start(self):
        self.target(*self.args)


def finding(page=1):
    return {'page':page,'category':'colour','title':'Primary colour','body':'Use the printed violet specification; the RGB and HEX disagree.',
            'scope':'Prime Forever','conditions':'Do not infer conversions','quote':'PF Violet','confidence':'medium'}


class ExtractionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=DocStore(Path(self.tmp.name,'test.db'))
        for name in ('A','B'):
            self.store.save_brand_profile(name,{'name':name,'swatches':[],'fonts':[],
                'identity':{'schemaVersion':1,'brandName':name,'cards':[]}})
        self.responses=[]
        def create(**request):
            self.assertEqual(request['model'],'claude-opus-4-8')
            raw=self.responses.pop(0) if self.responses else {'cards':[finding()]}
            if isinstance(raw,Exception):
                raise raw
            return SimpleNamespace(usage=SimpleNamespace(input_tokens=100,output_tokens=100),stop_reason='tool_use',
                                   content=[SimpleNamespace(type='tool_use',name='extract_identity',input=raw)])
        self.model=SimpleNamespace(messages=SimpleNamespace(create=create))
        self.app=FastAPI();self.app.include_router(identity_media.make_router(lambda:self.store))
        self.app.include_router(extraction.make_router(lambda:self.store,lambda:self.model))
        self.client=TestClient(self.app);self.addCleanup(self.client.close)
        self.source=self.client.post('/brands/A/sources',json={'filename':'Rules.pdf','data_b64':base64.b64encode(b'%PDF-1.4 fixture').decode()}).json()['id']
        self.prefix='/brands/A/extractions'
        for name,value in [('page_count',lambda data:8),('binary',lambda name:name),('render_batch',lambda *args:[]),('threading.Thread',InlineThread)]:
            patcher=patch('pdf_extraction.'+name,value);patcher.start();self.addCleanup(patcher.stop)

    def start(self,pages='1'):
        response=self.client.post(self.prefix,json={'source_id':self.source,'pages':pages})
        self.assertEqual(response.status_code,200,response.text)
        return self.client.get(self.prefix+'/'+response.json()['id']).json()

    def test_range_parser_bounds_and_dedup(self):
        self.assertEqual(extraction.parse_pages('1-3,2,8',8),[1,2,3,8])
        self.assertEqual(extraction.parse_pages('',3),[1,2,3])
        for value in ('0','9','3-1','1,,2','-1','1-999999999','a',None):
            with self.assertRaises(ValueError):extraction.parse_pages(value,8)
        with self.assertRaises(ValueError):extraction.parse_pages('',301)

    def test_job_records_source_model_pages_and_usage_without_changing_brand(self):
        before=self.store.get_brand_profile('A')
        run=self.start()
        self.assertEqual(run['status'],'done');self.assertEqual(run['completed_pages'],1)
        self.assertEqual(run['usage']['calls'],1);self.assertGreater(run['usage']['cost_usd'],0)
        card=run['cards'][0];self.assertEqual(card['status'],'draft')
        self.assertEqual(card['source']['sha256'],self.source);self.assertEqual(card['source']['page'],1)
        self.assertEqual(card['source']['quote'],'PF Violet')
        self.assertEqual(self.store.get_brand_profile('A'),before)
        self.assertEqual(self.store.get_identity_draft('A')['revision'],0)

    def test_import_is_draft_merge_idempotent_and_cannot_publish_unreviewed(self):
        run=self.start();cid=run['cards'][0]['id'];url=self.prefix+'/'+run['id']+'/import'
        r=self.client.post(url,json={'card_ids':[cid],'expected_revision':0});self.assertEqual(r.status_code,200,r.text)
        draft=r.json();self.assertEqual(draft['revision'],1)
        self.assertEqual(draft['profile']['swatches'],[]);self.assertEqual(draft['profile']['fonts'],[])
        self.assertNotIn('RGB and HEX disagree',design_markdown(draft['profile']))
        with self.assertRaises(WorkspaceConflict):self.store.publish_identity_draft('A',revision=1)
        duplicate=self.client.post(url,json={'card_ids':[cid],'expected_revision':1}).json()
        self.assertEqual(duplicate['revision'],1);self.assertEqual(len(duplicate['profile']['identity']['cards']),1)
        draft['profile']['identity']['cards'][0]['status']='reviewed'
        saved=self.store.save_identity_draft('A',draft['profile'],expected_revision=1)
        self.assertIn('RGB and HEX disagree',self.store.publish_identity_draft('A',revision=saved['revision'])['brand']['profile']['designPrinciples'])

    def test_stale_import_and_wrong_run_ids_do_not_replace_studio_edits(self):
        run=self.start();url=self.prefix+'/'+run['id']+'/import';cid=run['cards'][0]['id']
        profile=copy.deepcopy(self.store.get_identity_draft('A')['profile'])
        profile['identity']['cards'].append({'id':'studio','category':'guidance','title':'Studio note','body':'Retain this','scope':'Shared','status':'reviewed'})
        self.store.save_identity_draft('A',profile,expected_revision=0)
        self.assertEqual(self.client.post(url,json={'card_ids':[cid],'expected_revision':0}).status_code,409)
        self.assertEqual(self.client.post(url,json={'card_ids':['foreign'],'expected_revision':1}).status_code,422)
        self.assertEqual(self.client.post(url,json={'card_ids':[cid,cid],'expected_revision':1}).status_code,422)
        result=self.client.post(url,json={'card_ids':[cid],'expected_revision':1}).json()
        self.assertEqual(result['profile']['identity']['cards'][0]['id'],'studio')

    def test_brand_and_source_isolation(self):
        run=self.start()
        self.assertEqual(self.client.get('/brands/B/extractions/'+run['id']).status_code,404)
        self.assertEqual(self.client.get('/brands/B/extractions').json(),{'extractions':[]})
        self.assertEqual(self.client.post('/brands/B/extractions',json={'source_id':self.source,'pages':'1'}).status_code,404)
        self.assertEqual(self.client.post('/brands/B/extractions/'+run['id']+'/import',json={'card_ids':[run['cards'][0]['id']],'expected_revision':0}).status_code,404)
        self.assertEqual(self.client.get('/brands/B/sources/'+self.source+'/pdf-info').status_code,404)

    def test_invalid_model_output_retains_billed_usage_and_no_cards(self):
        self.responses=[{'cards':[finding(9)]}]
        run=self.start();self.assertEqual(run['status'],'failed');self.assertEqual(run['cards'],[])
        self.assertEqual(run['usage']['calls'],1);self.assertEqual(run['completed_pages'],0)

    def test_partial_failure_preserves_completed_batches_for_review(self):
        self.responses=[{'cards':[finding()]},RuntimeError('secret provider response')]
        run=self.start('1-8');self.assertEqual(run['status'],'failed')
        self.assertEqual(run['completed_pages'],4);self.assertEqual(len(run['cards']),1)
        self.assertEqual(run['usage']['calls'],1);self.assertNotIn('secret',run['error'])
        self.assertEqual(self.client.post(self.prefix+'/'+run['id']+'/import',json={'card_ids':[run['cards'][0]['id']],'expected_revision':0}).status_code,200)

    def test_empty_pages_are_successful_without_hallucinated_cards(self):
        self.responses=[{'cards':[]}];run=self.start()
        self.assertEqual(run['status'],'done');self.assertEqual(run['cards'],[])

    def test_duplicate_dispatch_for_active_brand_is_blocked(self):
        with patch('pdf_extraction.threading.Thread.start',lambda self:None):
            response=self.client.post(self.prefix,json={'source_id':self.source,'pages':'1'})
            self.assertEqual(response.status_code,200)
            self.assertEqual(self.client.post(self.prefix,json={'source_id':self.source,'pages':'1'}).status_code,409)
            self.assertEqual(self.client.post(self.prefix+'/'+response.json()['id']+'/import',json={'card_ids':['x'],'expected_revision':0}).status_code,409)

    def test_worker_restart_marks_incomplete_runs_recoverable(self):
        with patch('pdf_extraction.threading.Thread.start',lambda self:None):
            run=self.start()
        with TestClient(self.app):pass
        saved=self.client.get(self.prefix+'/'+run['id']).json()
        self.assertEqual(saved['status'],'failed');self.assertIn('restarted',saved['error'])

    def test_pdf_parse_failures_are_actionable_before_dispatch(self):
        with patch.object(extraction,'page_count',side_effect=ValueError('password protected')):
            self.assertEqual(self.client.post(self.prefix,json={'source_id':self.source,'pages':'1'}).status_code,422)
            self.assertEqual(self.client.get('/brands/A/sources/'+self.source+'/pdf-info').status_code,422)
        self.assertEqual(self.client.get(self.prefix).json(),{'extractions':[]})

    def test_model_cannot_assign_status_or_external_source(self):
        source={'id':'abc','brand':'A','filename':'Rules.pdf'}
        raw=finding();raw.update(status='reviewed',source={'url':'https://wrong.example'},assetNames=['foreign'])
        card=extraction.normalize_cards({'cards':[raw]},[1],source,'run')[0]
        self.assertEqual(card['status'],'draft');self.assertNotIn('assetNames',card)
        self.assertTrue(card['source']['url'].startswith('/api/brands/A/sources/abc'))

    def test_numeric_colour_evidence_never_overrides_working_palette(self):
        raw=finding();raw['body']='CMYK 35 | 25 | 13 | 1; HEX #B0B6CD. Source text disagrees.'
        card=extraction.normalize_cards({'cards':[raw]},[1],{'id':'abc','brand':'A','filename':'Guide.pdf'},'run')[0]
        self.assertEqual(card['origin'],'extracted-colour-values')
        card['status']='reviewed'
        profile={'name':'A','fonts':[],'swatches':[], 'identity':{'brandName':'A','cards':[card]}}
        self.assertNotIn('#B0B6CD',design_markdown(profile))


if __name__=='__main__':unittest.main()
