'use strict';
let companyOffset=0, companyTicket=0, compareTicket=0;
function showView(view){
  for(const name of ['explore','companies','compare']) $('view-'+name).hidden=name!==view;
  document.querySelectorAll('[data-view]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.view===view)));
  if(view==='companies') loadCompanies();
}
document.querySelectorAll('[data-view]').forEach(button=>button.onclick=()=>showView(button.dataset.view));
async function loadCompanies(){
  const ticket=++companyTicket;
  $('companyStatus').textContent='正在加载公司…';
  try{
    const result=await api('/api/intelligence/companies?'+new URLSearchParams({q:$('companyQuery').value.trim(),city:$('companyCity').value.trim(),offset:companyOffset,limit:12}));
    if(ticket!==companyTicket)return;
    $('companyStatus').textContent=`共 ${result.total} 家公司；仅包含有公司名称的已采集岗位。`;
    $('companyCards').replaceChildren();
    if(!result.items.length)$('companyCards').append(node('p','当前范围没有公司数据。','empty'));
    for(const company of result.items){
      const card=node('article',undefined,'companyCard');
      card.append(node('h3',company.company),node('p',`${company.jobs} 条岗位 · ${company.jd_jobs} 条有正文`),node('p','最近见到：'+time(company.last_seen),'muted'));
      const skills=node('div');
      for(const skill of company.skills)skills.append(node('span',`${skill.skill} · ${skill.jobs}/${company.jd_jobs}`,'tag'));
      if(!company.skills.length)skills.append(node('p','暂无正文技能依据。','muted'));
      const open=node('button','查看该公司岗位');
      open.onclick=()=>{
        $('company').value=company.company;$('query').value='';$('city').value=$('companyCity').value.trim();
        showView('explore');search();
      };
      card.append(skills,open);$('companyCards').append(card);
    }
    $('companyPrev').disabled=companyOffset===0;$('companyNext').disabled=companyOffset+12>=result.total;
    $('companyPage').textContent=`${Math.floor(companyOffset/12)+1} / ${Math.max(1,Math.ceil(result.total/12))}`;
  }catch(error){if(ticket===companyTicket){$('companyStatus').textContent='加载失败：'+error.message;$('companyCards').replaceChildren();}}
}
$('companySearch').onclick=()=>{companyOffset=0;loadCompanies();};
for(const id of ['companyQuery','companyCity'])$(id).onkeydown=e=>{if(e.key==='Enter'){companyOffset=0;loadCompanies();}};
$('companyPrev').onclick=()=>{companyOffset=Math.max(0,companyOffset-12);loadCompanies();};
$('companyNext').onclick=()=>{companyOffset+=12;loadCompanies();};
function table(headers,rows){
  const wrap=node('div',undefined,'tableWrap'),table=node('table'),head=node('thead'),headRow=node('tr'),body=node('tbody');
  for(const text of headers)headRow.append(node('th',text));
  head.append(headRow);table.append(head);
  for(const row of rows){const tr=node('tr');for(const text of row)tr.append(node('td',text));body.append(tr);}
  table.append(body);wrap.append(table);return wrap;
}
const percentage=value=>value===null?'暂无数据':(value*100).toFixed(1)+'%';
function cohort(prefix){return {keyword:$(prefix+'Keyword').value.trim(),city:$(prefix+'City').value.trim(),company:$(prefix+'Company').value.trim()};}
$('compareForm').onsubmit=async event=>{
  event.preventDefault();const ticket=++compareTicket;$('compareRun').disabled=true;
  $('compareStatus').textContent='正在分析两组样本…';
  for(const id of ['compareWarnings','compareSummary','compareResults'])$(id).replaceChildren();
  try{
    const result=await api('/api/intelligence/compare',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({left:cohort('left'),right:cohort('right')})});
    if(ticket!==compareTicket)return;
    $('compareStatus').textContent=`分析完成 · ${result.overlap_jobs} 条岗位重叠 · 比例差为 A 组减 B 组（百分点），不代表需求增长。`;
    for(const warning of result.warnings)$('compareWarnings').append(node('p',warning,'notice'));
    for(const [name,group] of [['A',result.left],['B',result.right]]){
      const summary=node('article',undefined,'summaryCard');
      summary.append(node('h3',name+' 组'),node('p',Object.values(group.scope).filter(Boolean).join(' · ')||'全部样本'),node('strong',group.jobs+' 条岗位'),node('p',`${group.companies} 家公司 · ${group.jd_jobs} 条有正文 · 覆盖率 ${percentage(group.coverage)}`));
      $('compareSummary').append(summary);
    }
    const output=$('compareResults');output.append(node('h3','技能需求差异（正文依据）'));
    if(!result.skills.length)output.append(node('p','尚无正文技能可供比较，请先采集或补充 JD。','empty'));
    else output.append(table(['技能','A 组岗位数','A 组提及率','B 组岗位数','B 组提及率','差值（百分点）'],result.skills.map(s=>[s.skill,s.left_jobs,percentage(s.left_rate),s.right_jobs,percentage(s.right_rate),s.difference_pp===null?'不可比较':(s.difference_pp>0?'+':'')+s.difference_pp.toFixed(1)])));
    for(const [key,title] of [['experience','经验要求分布'],['education','学历要求分布']]){
      output.append(node('h3',title+'（全部岗位；含未记录）'));
      const left=new Map(result.left[key].map(x=>[x.label,x.jobs])),right=new Map(result.right[key].map(x=>[x.label,x.jobs]));
      const labels=[...new Set([...left.keys(),...right.keys()])];
      output.append(table(['要求','A 组岗位数','B 组岗位数'],labels.map(label=>[label,left.get(label)||0,right.get(label)||0])));
    }
  }catch(error){if(ticket===compareTicket)$('compareStatus').textContent='分析失败：'+error.message;}
  finally{if(ticket===compareTicket)$('compareRun').disabled=false;}
};
