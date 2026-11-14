'use strict';
let heatData=null, heatUpdated=null, heatBusy=false;
function heatmapStatus() {
  $('heatStatus').classList.remove('error');
  $('heatStatus').textContent=(heatUpdated ? '最近同步：'+heatUpdated.toLocaleTimeString('zh-CN',{hour12:false})+' · ' : '')+
    ($('heatAuto').checked ? '每 30 秒读取本地最新数据（仅当前可见工作区）' : '自动更新已暂停，可点击顶部刷新数据');
}
function clearHeatmap() {
  heatData=null;
  $('heatGrid').replaceChildren(node('p','正在更新当前筛选范围…','empty'));
  $('heatScope').textContent='正在读取当前筛选条件下的技能需求';
  $('heatMax').textContent='多';
  $('heatStatus').textContent='正在同步…';
}
function acceptHeatmap(data) {
  heatData=data;heatUpdated=new Date();heatmapStatus();
}
function heatmapFailure() {
  $('heatStatus').classList.add('error');
  $('heatStatus').textContent='同步失败 · '+(heatData?'仍显示 '+heatUpdated.toLocaleTimeString('zh-CN',{hour12:false})+' 的数据':'暂无当前范围的数据')+'；请检查本地服务，稍后自动重试或点击刷新数据。';
}
function renderHeatmap() {
  if(!heatData)return;
  const grid=$('heatGrid'), active=document.activeElement?.dataset?.heatSkill;
  grid.replaceChildren();
  const items=heatData.items.slice(0,Number($('heatLimit').value));
  const maximum=Math.max(0,...items.map(item=>item.jobs));
  $('heatMax').textContent=maximum;
  const scope=[state.q&&'关键词：'+state.q,state.city&&'城市：'+state.city,state.company&&'公司：'+state.company].filter(Boolean).join(' · ')||'全部已采集样本';
  $('heatScope').textContent=`${scope} · ${heatData.source==='jd'?'正文':'标题与标签'}依据 · ${heatData.total_jobs} 条岗位为分母 / ${heatData.sampled_jobs} 条样本 · 显示 ${items.length} 项技能`;
  if(!items.length)grid.append(node('p',heatData.source==='jd'?'当前范围暂无正文技能数据，请先采集或补充岗位正文。':'当前范围暂无技能提及。','empty'));
  for(const item of items){
    const level=Math.max(1,Math.ceil(item.jobs/maximum*5));
    const button=node('button',undefined,'heatCell heatLevel'+level);
    button.type='button';button.dataset.heatSkill=item.skill;
    button.setAttribute('aria-pressed',String(state.skill===item.skill));
    const label=`${item.skill}：${item.jobs} 个岗位，占当前分母 ${(item.rate*100).toFixed(1)}%`;
    button.setAttribute('aria-label',label);button.title=label;
    button.append(node('span',item.skill,'heatName'),node('strong',item.jobs),node('span',`个岗位 · ${(item.rate*100).toFixed(1)}%`,'heatRate'));
    button.onclick=()=>{state.skill=state.skill===item.skill?'':item.skill;state.offset=0;renderSkills();loadJobs().catch(fail);};
    grid.append(button);
    if(active===item.skill)button.focus({preventScroll:true});
  }
}
async function pollHeatmap() {
  if(heatBusy||!$('heatAuto').checked||document.hidden||$('view-explore').hidden||$('refresh').disabled)return;
  heatBusy=true;
  const request=state.request, query=params({limit:50}).toString();
  try{
    const data=await api('/api/stats/skills?'+query);
    if(request!==state.request||query!==params({limit:50}).toString()||!$('heatAuto').checked)return;
    state.skills=data.items;acceptHeatmap(data);renderSkills();
    $('denominator').textContent=data.source==='jd'?`分母：当前范围有正文的 ${data.total_jobs} 条岗位；共搜集 ${data.sampled_jobs} 条。`:`分母：当前范围全部 ${data.total_jobs} 条岗位；仅使用标题与标签，不能替代任职要求分析。`;
  }catch(error){if(request===state.request)heatmapFailure();}
  finally{heatBusy=false;}
}
document.addEventListener('DOMContentLoaded',()=>{
  $('heatLimit').onchange=renderHeatmap;
  $('heatAuto').onchange=()=>{heatmapStatus();if($('heatAuto').checked)pollHeatmap();};
  setInterval(pollHeatmap,30000);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)pollHeatmap();});
});
