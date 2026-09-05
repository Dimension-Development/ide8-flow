"""Live-trial failure regressions; deterministic clients, no paid requests."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from generation import prompts
from generation.loop import GenConfig, generate_concept
from generation.mutation import mutate_document
from generation.render_client import CompileRejected
from generation.service import generate_and_store
from schema_registry import load
from store import DocStore
from validation import contrast, geometry
from test_generation_loop import FakeRender, ScriptedClient, critique_resp, emit_resp


PROFILE = {'swatches': [
    {'name': 'Charcoal', 'space': 'cmyk', 'values': [20, 20, 25, 70]},
    {'name': 'White', 'space': 'cmyk', 'values': [0, 0, 0, 0]},
    {'name': 'Pale Violet Darkest', 'space': 'cmyk', 'values': [45, 34, 18, 3]},
], 'rules': {'contrastFloor': 3.0}}


def doc():
    return {'version': '0.2', 'page': {'size': 'A4'}, 'pages': [{'items': []}]}


def dependencies(client, render=None, **kwargs):
    route = load('0.2')
    return dict(client=client, render=render or FakeRender(), pack=route['pack'],
                schema_json=route['schema_json'], schema_path=route['schema_path'],
                expected_version='0.2', **kwargs)


class PromptContract(unittest.TestCase):
    def test_asset_fit_guidance_matches_both_schema_routes(self):
        assets = [{'name': 'cutout', 'width': 200, 'height': 400}]
        for version in ('0.1', '0.2'):
            client = ScriptedClient([emit_resp({**doc(), 'version': version}), critique_resp(True)])
            route = load(version)
            generate_concept({}, PROFILE, 'test', client=client, render=FakeRender(),
                             pack=route['pack'], schema_json=route['schema_json'],
                             schema_path=route['schema_path'], expected_version=version,
                             assets={'cutout': {**assets[0], 'mime': 'image/png', 'data': b''}})
            message = client.calls[0]['messages'][0]['content']
            if version == '0.2':
                self.assertIn('fit "contain"', message)
                self.assertNotIn('fit "frame"', message)
            else:
                self.assertIn('fit "frame"', message)

    def test_geometry_instructions_produce_valid_full_bleed_frame(self):
        for spec in ({'size': 'A4', 'bleed': 8.5},
                     {'size': 'A4', 'orientation': 'landscape', 'bleed': 8.5},
                     {'trimMm': [210, 297], 'bleedMm': 3, 'safeAreaMm': 5}):
            text = prompts.geometry_section(spec)
            values = json.loads(next(line for line in text.splitlines() if line.startswith('{')))
            from validation.format_check import normalize_format
            page = normalize_format(spec)
            errors, _ = geometry.check({'page': page, 'pages': [{'items': [
                {'type': 'shape', 'frame': values['full_bleed_frame']}]}]}, PROFILE)
            self.assertEqual(errors, [])
        a4 = prompts.geometry_section({'size': 'A4', 'bleed': 8.5})
        self.assertIn('[-8.5, -8.5, 612.0, 859.0]', a4)

    def test_asset_roles_are_next_to_names(self):
        text = prompts.assets_section([{'name': 'violet-field'}], version='0.2',
                                      asset_notes=[{'name': 'violet-field', 'description': 'Gradient background; no product.'}])
        self.assertIn('violet-field — Gradient background; no product.', text)

    def test_advised_colour_pairs_pass_the_same_validator(self):
        pairs = contrast.solid_pairings(PROFILE)
        self.assertTrue(pairs)
        self.assertFalse(any(p['text'] == 'White' and p['background'] == 'Pale Violet Darkest' for p in pairs))
        for pair in pairs:
            document = self.colour_doc(pair['text'], pair['background'])
            self.assertEqual(contrast.check(document, PROFILE), [])

    @staticmethod
    def colour_doc(text, background):
        return {'swatches': PROFILE['swatches'],
                'charStyles': [{'name': 'Text', 'color': text}],
                'paraStyles': [{'name': 'Body', 'charStyle': 'Text'}],
                'pages': [{'items': [{'type': 'text', 'frame': [0, 0, 50, 20], 'fill': background,
                                     'paragraphs': [{'style': 'Body', 'text': 'Headline'}]}]}]}

    def test_contrast_failure_names_usable_brand_alternative_without_changing_art(self):
        document = self.colour_doc('White', 'Pale Violet Darkest')
        original = copy.deepcopy(document)
        error = contrast.check(document, PROFILE)[0]
        self.assertEqual(error['code'], 'low-contrast')
        self.assertIn('2.57', error['message'])
        self.assertIn("'Charcoal'", error['message'])
        self.assertEqual(document, original)


class RepairLoop(unittest.TestCase):
    def test_missing_version_escalates_and_supplies_explicit_root_instructions(self):
        missing = doc(); del missing['version']
        client = ScriptedClient([emit_resp(missing), emit_resp(missing), emit_resp(doc()), critique_resp(True)])
        result = generate_concept({}, PROFILE, 'test', **dependencies(client))
        self.assertTrue(result.approved)
        self.assertEqual(client.calls[2]['model'], GenConfig().strong_model)
        feedback = json.loads(client.calls[1]['messages'][-1]['content'][0]['content'])
        self.assertIn('"version": "0.2"', feedback['errors'][0]['message'])
        self.assertEqual(result.validation['attempts'][0]['emitted_document'], missing)
        self.assertEqual(result.validation['attempts'][0]['stop_reason'], 'tool_use')

    def test_wrapped_document_is_retained_but_not_silently_unwrapped_or_rendered(self):
        render = FakeRender()
        wrapped = {'document': doc()}
        with tempfile.TemporaryDirectory() as tmp:
            store = DocStore(Path(tmp) / 'trial.db')
            result = generate_and_store({}, n=1, store=store, profile=PROFILE,
                                        **dependencies(ScriptedClient([emit_resp(wrapped)]), render,
                                                       config=GenConfig(max_iterations=1)))
            concept = store.get_concept(result['concepts'][0]['concept_id'])
            failure = concept['failure']['validation']
            self.assertEqual(failure['errors'][0]['code'], 'document-version-mismatch')
            self.assertEqual(failure['attempts'][0]['emitted_document'], wrapped)
            self.assertIsNone(result['concepts'][0]['version_id'])
        self.assertEqual(render.compiled, [])

    def test_truncated_emission_is_not_a_version_error_or_a_valid_candidate(self):
        truncated = emit_resp(doc()); truncated.stop_reason = 'max_tokens'
        render = FakeRender()
        result = generate_concept({}, PROFILE, 'test', **dependencies(
            ScriptedClient([truncated]), render, config=GenConfig(max_iterations=1)))
        self.assertEqual(result.validation['errors'][0]['code'], 'incomplete-document')
        self.assertIsNone(result.document)
        self.assertEqual(render.compiled, [])

    def test_render_failures_also_escalate(self):
        class RejectRender(FakeRender):
            def compile(self, document, image_meta=None):
                raise CompileRejected([{'code': 'compile', 'path': '$', 'message': 'reject'}])
        for render in (RejectRender(), FakeRender(overflow_rounds=[[{'item': 'headline', 'page': 1}]] * 3)):
            client = ScriptedClient([emit_resp(doc()) for _ in range(3)])
            result = generate_concept({}, PROFILE, 'test', **dependencies(client, render, config=GenConfig(max_iterations=3)))
            self.assertEqual(client.calls[2]['model'], GenConfig().strong_model)
            self.assertIsNone(result.document)

    def test_mutation_uses_same_contract_and_records_failed_candidate(self):
        missing = doc(); del missing['version']
        client = ScriptedClient([emit_resp(missing), emit_resp(doc())])
        result = mutate_document(doc(), 'retain layout', PROFILE, **dependencies(client))
        self.assertIsNotNone(result.document)
        self.assertEqual(client.calls[1]['model'], GenConfig().strong_model)
        self.assertEqual(result.validation['attempts'][0]['emitted_document'], missing)


if __name__ == '__main__':
    unittest.main()
