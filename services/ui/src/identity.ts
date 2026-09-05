import type {IdentityCard, IdentityProfile, Swatch} from './api';

export function swatchColor(s:Swatch):string {
  if (s.space==='rgb') return `rgb(${s.values.join(',')})`;
  const [c,m,y,k]=s.values.map(v=>v/100);
  return `rgb(${[c,m,y].map(v=>Math.round(255*(1-v)*(1-k))).join(',')})`;
}
export function identityCards(profile:IdentityProfile):IdentityCard[] {
  if (profile.identity) return profile.identity.cards;
  return profile.designPrinciples ? [{id:'legacy-direction',category:'guidance',title:'Existing creative direction',body:profile.designPrinciples,status:'provisional',scope:'Brand',source:{label:'Existing published profile'}}] : [];
}
export function designMarkdown(profile:IdentityProfile):string {
  const id=profile.identity;
  const lines=[`# ${id?.brandName || profile.name} — design guidance`, '',
    id?.campaignName ? `Campaign: ${id.campaignName}` : '',
    'Apply guidance only within its stated campaign, range and channel. Provisional interpretations are for internal review; reviewed interpretations are not client artwork approval. Draft and rejected cards are excluded. Numeric rules are enforced only where the application implements the corresponding validator.', '',
    '## Published-package colour definitions', '', ...profile.swatches.map(s=>`- ${s.name}: ${s.space.toUpperCase()} ${s.values.join(' / ')}${s.spot?' (spot)':''}`), '',
    '## Font references', '', ...profile.fonts.map(f=>`- ${f}`), '', '## Creative guidance', ''];
  for (const card of identityCards(profile).filter(c=>c.status!=='draft'&&c.status!=='rejected'&&c.origin!=='extracted-colour-values')) {
    lines.push(`### ${card.title} [${card.id}]`, `Scope: ${card.scope || 'Unspecified'} · Status: ${card.status}`, '', card.body, '');
    if (card.conditions) lines.push(`Conditions: ${Array.isArray(card.conditions)?card.conditions.join('; '):card.conditions}`, '');
    if (card.source) lines.push(`Source: ${card.source.label}${card.source.page?`, page ${card.source.page}`:''}`, '');
  }
  return lines.filter((l,i)=>l!==''||lines[i-1]!=='').join('\n');
}
export function downloadText(name:string,text:string) {
  const url=URL.createObjectURL(new Blob([text],{type:'text/markdown;charset=utf-8'}));
  const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
