import { useEffect, useState } from 'react';
import ConceptGrid from './components/ConceptGrid';
import ConceptDetail from './components/ConceptDetail';
import BriefForm from './components/BriefForm';
import AssetsView from './components/AssetsView';
import BrandsView from './components/BrandsView';
import Dashboard from './components/Dashboard';
import StudioHome from './components/StudioHome';
import ProjectWorkspace from './components/ProjectWorkspace';
import BrandWorkspace from './components/BrandWorkspace';
import ClientReview from './components/ClientReview';
import {api} from './api';

type View = {kind:'studio'|'grid'|'assets'|'brands'|'stats'|'new-brand'}
 | {kind:'brand';name:string} | {kind:'project';id:string} | {kind:'review';token:string}
 | {kind:'concept';id:string;projectId?:string} | {kind:'brief';projectId?:string};
function initialView():View {
 try {const h=new URLSearchParams(location.hash.slice(1));if(h.has('review')||document.documentElement.dataset.reviewOnly==='true')return {kind:'review',token:h.get('review')||''}; if(h.get('brand'))return {kind:'brand',name:h.get('brand')!};if(h.get('project'))return {kind:'project',id:h.get('project')!};}catch{}
 return {kind:'studio'};
}
function NewBrand({onCreated,onBack}:{onCreated:(name:string)=>void;onBack:()=>void}){
 const [name,setName]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 return <div className="mx-auto max-w-xl rounded-3xl border border-ink/10 bg-white p-8"><button onClick={onBack} className="text-sm text-ink-soft">← Studio</button><h1 className="mt-6 font-serif text-3xl">Create a brand workspace</h1><p className="my-4 text-sm leading-relaxed text-ink-soft">Start with a name, then attach source guidelines, assign imagery and review its identity. No colours or fonts are invented for you.</p><form className="space-y-4" onSubmit={async e=>{e.preventDefault();setBusy(true);setError('');try{const brands=await api.brands();if(brands.brands.some(b=>b.name===name.trim()))throw new Error('A brand with this name already exists.');await api.saveBrand({name:name.trim(),swatches:[],fonts:[],rules:{},identity:{schemaVersion:1,brandName:name.trim(),cards:[]}});onCreated(name.trim());}catch(e){setError(String(e));}finally{setBusy(false)}}}><label className="block text-sm">Brand name<input required autoFocus className="mt-2 w-full rounded-xl border border-ink/15 p-3" value={name} onChange={e=>setName(e.target.value)}/></label>{error&&<p role="alert" className="text-brand">{error}</p>}<button disabled={busy||!name.trim()} className="rounded-xl bg-ink px-5 py-3 text-sm font-semibold text-white disabled:opacity-40">{busy?'Creating…':'Create brand'}</button></form></div>
}
export default function App(){
 const [view,setView]=useState<View>(initialView),[activeJobId,setActiveJobId]=useState<string|null>(null),[identityDirty,setIdentityDirty]=useState(false);
 useEffect(()=>{if(!identityDirty)return;const warn=(e:BeforeUnloadEvent)=>{e.preventDefault();e.returnValue='';};window.addEventListener('beforeunload',warn);return()=>window.removeEventListener('beforeunload',warn);},[identityDirty]);
 useEffect(()=>{const sync=()=>{if(identityDirty&&!window.confirm('Leave this identity draft without saving your changes?')){const old=new URLSearchParams();if(view.kind==='brand')old.set('brand',view.name);history.replaceState(null,'',`${location.pathname}${location.search}${old.size?'#'+old.toString():''}`);return;}setIdentityDirty(false);setView(initialView());};window.addEventListener('hashchange',sync);window.addEventListener('popstate',sync);return()=>{window.removeEventListener('hashchange',sync);window.removeEventListener('popstate',sync);};},[identityDirty,view]);
 const go=(next:View)=>{if(identityDirty&&!window.confirm('Leave this identity draft without saving your changes?'))return;setIdentityDirty(false);setView(next);const h=new URLSearchParams();if(next.kind==='brand')h.set('brand',next.name);if(next.kind==='project')h.set('project',next.id);if(next.kind==='concept'&&next.projectId)h.set('project',next.projectId);history.replaceState(null,'',`${location.pathname}${location.search}${h.size?'#'+h.toString():''}`)};
 const studio=()=>go({kind:'studio'}),brand=(name:string)=>go({kind:'brand',name}),project=(id:string)=>go({kind:'project',id});
 if(view.kind==='review')return <div data-client-review><style>{`#benchmark-banner{display:none}`}</style><ClientReview token={view.token}/></div>;
 return <div className="min-h-screen"><header className="sticky top-0 z-30 border-b border-ink/10 bg-paper/95 backdrop-blur"><div className="mx-auto flex max-w-[1440px] flex-wrap items-center gap-5 px-6 py-4"><button onClick={studio} className="font-serif text-2xl font-bold">ide8<span className="text-brand">.flow</span></button><span className="border-l border-ink/15 pl-5 text-xs uppercase tracking-[.18em] text-ink-soft">Studio workspace</span><nav aria-label="Studio navigation" className="ml-auto flex flex-wrap gap-4 text-sm"><button onClick={studio}>Brands & projects</button><button onClick={()=>go({kind:'grid'})}>All artwork</button><button onClick={()=>go({kind:'assets'})}>Asset intake</button><button onClick={()=>go({kind:'stats'})}>Usage</button><button onClick={()=>go({kind:'brands'})} className="text-ink-soft">Profile settings</button></nav></div></header><main className="mx-auto max-w-[1440px] px-6 py-8">
 {view.kind==='studio'?<StudioHome onOpenBrand={brand} onOpenProject={project} onCreateBrand={()=>go({kind:'new-brand'})}/>
 :view.kind==='new-brand'?<NewBrand onCreated={brand} onBack={studio}/>
 :view.kind==='brand'?<BrandWorkspace key={view.name} name={view.name} onDirtyChange={setIdentityDirty} onBack={studio} onOpenProject={project}/>
 :view.kind==='project'?<ProjectWorkspace key={view.id} projectId={view.id} onBack={studio} onOpenBrand={brand} onEditBrief={id=>go({kind:'brief',projectId:id})} onOpenConcept={id=>go({kind:'concept',id,projectId:view.id})} activeJobId={activeJobId} onJobSettled={()=>setActiveJobId(null)}/>
 :view.kind==='brief'?<BriefForm key={view.projectId||'new'} initialProjectId={view.projectId} onStarted={(jobId,projectId)=>{setActiveJobId(jobId);if(projectId)project(projectId);else go({kind:'grid'});}}/>
 :view.kind==='grid'?<ConceptGrid activeJobId={activeJobId} onJobSettled={()=>setActiveJobId(null)} onOpen={id=>go({kind:'concept',id})}/>
 :view.kind==='concept'?<ConceptDetail conceptId={view.id} onBack={()=>view.projectId?project(view.projectId):go({kind:'grid'})}/>
 :view.kind==='assets'?<AssetsView/>:view.kind==='brands'?<BrandsView/>:<Dashboard/>}
 </main></div>
}
