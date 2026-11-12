'use strict';
const $ = id => document.getElementById(id);
const state = {q: '', city: '', company: '', source: 'jd', skill: '', offset: 0, limit: 20, total: 0, skills: [], request: 0};
function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
}
function safeUrl(value) {
  try {
    const url = new URL(value);
    return url.protocol === 'https:' && url.host === 'www.zhipin.com' && /^\/job_detail\/[\w-]+\.html$/.test(url.pathname) ? url.href : null;
  } catch { return null; }
}
function time(value) { return value ? value.replace('T', ' ') : '未记录'; }
async function api(url, options) {
  const response = await fetch(url, {...options, signal: AbortSignal.timeout(15000)});
  const data = await response.json();
  if (!response.ok || data.ok !== true) {
    const reason = data.detail?.reason || data.reason || ('HTTP ' + response.status);
    throw new Error(reason);
  }
  return data;
}
function params(extra = {}) { return new URLSearchParams({q: state.q, city: state.city, company: state.company, source: state.source, ...extra}); }
function fail(error) { $('status').textContent = '加载失败：' + error.message + '。请检查本地服务后重试。'; $('status').classList.add('error'); }
function renderSkills() {
  $('skills').replaceChildren();
  $('clearSkill').hidden = !state.skill;
  if (!state.skills.length) $('skills').append(node('p', state.source === 'jd' ? '当前范围暂无正文技能数据。请浏览详情页，或在下方粘贴岗位正文。' : '当前范围暂无匹配到的技能。', 'empty'));
  for (const item of state.skills) {
    const button = node('button', undefined, 'skill' + (state.skill === item.skill ? ' active' : ''));
    button.setAttribute('aria-pressed', String(state.skill === item.skill));
    const line = node('span', undefined, 'line');
    line.append(node('span', item.skill), node('span', `${item.jobs} 个 · ${(item.rate * 100).toFixed(1)}%`));
    const track = node('div', undefined, 'track'), fill = node('div', undefined, 'fill');
    fill.style.width = `${Math.max(0, Math.min(100, item.rate * 100))}%`;
    track.append(fill); button.append(line, track);
    button.onclick = () => {state.skill = state.skill === item.skill ? '' : item.skill; state.offset = 0; renderSkills(); loadJobs().catch(fail);};
    $('skills').append(button);
  }
}
function renderJobs(data) {
  state.total = data.total;
  $('listCount').textContent = `共 ${data.total} 条 · 本页 ${data.count} 条`;
  $('filterHint').textContent = state.skill ? `技能筛选：${state.skill}（${state.source === 'jd' ? '正文' : '标题/标签'}）；左侧比例仍以当前城市与搜索范围计算。` : '查看原文依据，或返回招聘页面自行核验在招状态。';
  $('jobs').replaceChildren();
  if (!data.items.length) $('jobs').append(node('p', '当前筛选范围没有岗位。', 'empty'));
  for (const job of data.items) {
    const card = node('article', undefined, 'job');
    const heading = node('div', undefined, 'jobHead');
    heading.append(node('h3', job.title), node('span', job.has_jd ? '正文已收录' : '待补充正文', 'jdBadge' + (job.has_jd ? ' complete' : '')));
    card.append(heading, node('p', job.company || '公司待补齐', 'jobCompany'));
    card.append(node('p', [job.area || job.city || '城市未记录', job.exp, job.degree].filter(Boolean).join(' · '), 'jobLocation'));
    card.append(node('p', job.salary_masked ? '薪资数字不可识别（不参与统计）' : job.salary || '薪资未记录', 'salary'));
    const tags = node('div');
    for (const tag of job.tags || []) tags.append(node('span', tag, 'tag'));
    card.append(tags, node('p', `最近见到：${time(job.last_seen)}`, 'jobTime'));
    const actions = node('div', undefined, 'actions');
    const detail = node('button', '查看正文与技能依据');
    detail.onclick = () => showDetail(job.job_key).catch(fail);
    const add = node('button', job.has_jd ? '更新正文' : '补充正文');
    add.onclick = () => {$('jdUrl').value = safeUrl(job.url) || ''; $('jdText').value = ''; $('jdText').focus(); $('jdForm').scrollIntoView({behavior:'smooth',block:'center'});};
    actions.append(detail, add);
    const href = safeUrl(job.url);
    if (href) { const link = node('a', '打开 BOSS 原页面 ↗'); link.href = href; link.target = '_blank'; link.rel = 'noopener noreferrer'; actions.append(link); }
    card.append(actions); $('jobs').append(card);
  }
  $('prev').disabled = state.offset === 0;
  $('next').disabled = state.offset + state.limit >= state.total;
  $('pageNumber').textContent = `${Math.floor(state.offset/state.limit)+1} / ${Math.max(1,Math.ceil(state.total/state.limit))}`;
}
let jobsRequest = 0;
async function loadJobs() {
  const ticket = ++jobsRequest;
  const data = await api('/api/jobs?' + params({skill:state.skill,limit:state.limit,offset:state.offset}));
  if (ticket === jobsRequest) renderJobs(data);
}
async function refresh() {
  const ticket = ++state.request;
  $('status').classList.remove('error'); $('status').textContent = '正在更新数据…';
  $('refresh').disabled = true;
  try {
    const [overview, skills, cities] = await Promise.all([api('/api/stats/overview'), api('/api/stats/skills?' + params({limit:50})), api('/api/filters/cities')]);
    if (ticket !== state.request) return;
    $('cityOptions').replaceChildren();
    for (const item of cities.items) {
      const option = node('option'); option.value = item.city;
      option.label = `${item.city} · ${item.jobs} 条样本`;
      $('cityOptions').append(option);
    }
    $('cityHint').textContent = state.city ? `当前筛选：${state.city}；点击“全部”清除` : `全部城市 · 已采集 ${cities.items.length} 个城市`;
    $('jobsCount').textContent = overview.jobs;
    $('companiesCount').textContent = overview.companies;
    $('jdCount').textContent = `${overview.jd_jobs} / ${overview.jobs ? (overview.jd_jobs / overview.jobs * 100).toFixed(0) : 0}%`;
    $('coverageFill').style.width = `${overview.jobs ? Math.min(100,overview.jd_jobs/overview.jobs*100) : 0}%`;
    $('lastSeen').textContent = time(overview.last_seen);
    state.skills = skills.items;
    $('skillsTitle').textContent = state.source === 'jd' ? '岗位正文技能提及' : '标题与标签技能分布';
    $('denominator').textContent = state.source === 'jd' ? `分母：当前范围有正文的 ${skills.total_jobs} 条岗位；共搜集 ${skills.sampled_jobs} 条。` : `分母：当前范围全部 ${skills.total_jobs} 条岗位；仅使用标题与标签，不能替代任职要求分析。`;
    renderFilterChips(); renderSkills(); await loadJobs();
    if (ticket === state.request) $('status').textContent = '已同步本地数据 · 总览为全部样本，列表与分析按条件筛选';
  } catch (error) {if(ticket === state.request) fail(error);}
  finally {if(ticket === state.request) $('refresh').disabled = false;}
}

function renderFilterChips() {
  $('activeFilters').replaceChildren();
  for (const [field,label,id] of [['q','关键词','query'],['city','城市','city'],['company','公司','company']]) {
    if (!state[field]) continue;
    const chip = node('button', `${label}：${state[field]} ×`, 'filterChip');
    chip.setAttribute('aria-label', `清除${label}条件：${state[field]}`);
    chip.onclick = () => {$(id).value='';search();};
    $('activeFilters').append(chip);
  }
}
let detailRequest = 0;
async function showDetail(key) {
  const ticket = ++detailRequest;
  $('detailTitle').textContent = '正在加载…'; $('detailBody').textContent = ''; $('detailMeta').textContent = ''; $('evidence').replaceChildren();
  if (!$('detailDialog').open) $('detailDialog').showModal();
  try {
    const detail = await api('/api/jobs/' + encodeURIComponent(key) + '/detail');
    if (ticket !== detailRequest) return;
    $('detailTitle').textContent = detail.job.title;
    $('detailMeta').textContent = `${detail.job.company || '公司待补齐'} · 正文采集时间：${time(detail.captured_at)}`;
    $('detailBody').textContent = detail.jd_text || '尚未采集岗位正文。请浏览该岗位详情页或使用下方的正文录入入口。';
    const names = {jd:'正文',tag:'列表标签',title:'岗位标题'};
    for (const hit of detail.skills) {
      const row = node('div',undefined,'evidence');
      row.append(node('strong',`${hit.skill} · ${names[hit.source] || hit.source}`),node('p',hit.evidence));
      $('evidence').append(row);
    }
    if (!detail.skills.length) $('evidence').append(node('p','暂无技能匹配结果。','muted'));
  } catch(error) {if(ticket === detailRequest) $('detailBody').textContent = '详情加载失败：' + error.message;}
}
function search() {state.q=$('query').value.trim();state.city=$('city').value.trim();state.company=$('company').value.trim();state.source=$('source').value;state.skill='';state.offset=0;refresh();}
$('search').onclick=search;
$('resetFilters').onclick=()=>{for(const id of ['query','city','company'])$(id).value='';search();};
$('openImport').onclick=()=>{
  if(typeof showView === 'function') showView('explore');
  $('importSection').scrollIntoView({behavior:'smooth',block:'start'});
  $('jdUrl').focus({preventScroll:true});
};
$('city').onchange=search;
$('city').addEventListener('search',()=>{if (!$('city').value) search();});
$('clearCity').onclick=()=>{$('city').value='';search();};
$('source').onchange=search;
for (const id of ['query','city','company']) $(id).onkeydown=e=>{if(e.key==='Enter') search();};
$('refresh').onclick=async()=>{
  await refresh();
  if(!$('view-companies').hidden && typeof loadCompanies==='function') await loadCompanies();
};
$('clearSkill').onclick=()=>{state.skill='';state.offset=0;renderSkills();loadJobs().catch(fail);};
$('prev').onclick=()=>{state.offset=Math.max(0,state.offset-state.limit);loadJobs().catch(fail);};
$('next').onclick=()=>{state.offset+=state.limit;loadJobs().catch(fail);};
$('closeDetail').onclick=()=>{$('detailDialog').close();detailRequest++;};
$('jdForm').onsubmit=async event=>{
  event.preventDefault();
  const url=safeUrl($('jdUrl').value.trim()),jd=$('jdText').value.trim();
  $('importStatus').classList.remove('error');
  if(!url||jd.length<20){$('importStatus').textContent='请输入有效的 BOSS 职位链接和至少 20 字正文。';return;}
  $('saveJd').disabled=true;$('importStatus').textContent='正在保存…';
  try {
    await api('/api/import/jd',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url,jd_text:jd})});
    $('importStatus').textContent='已保存，正文技能已重新分析。';await refresh();
  } catch(error){$('importStatus').classList.add('error');$('importStatus').textContent='保存失败：'+error.message;}
  finally{$('saveJd').disabled=false;}
};
refresh();
