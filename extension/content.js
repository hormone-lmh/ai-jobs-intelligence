// 不主动访问招聘站；读取当前用户已展开的职位内容。
(function () {
  let inflight=false, failures=0, retryAt=0;
  const sent=new Map();
  const text=el=>(el?.innerText||el?.textContent||'').trim();
  const badge=document.createElement('div');
  badge.id='jobs-intel-status';badge.setAttribute('role','status');
  badge.style.cssText='position:fixed;right:18px;bottom:18px;z-index:2147483647;padding:10px 14px;max-width:350px;background:#123c36;color:white;font:13px/1.5 sans-serif;border-radius:8px;box-shadow:0 2px 12px #0003;pointer-events:none';
  document.documentElement.append(badge);
  const status=message=>{badge.textContent='岗位采集 v1.2 · '+message;};
  async function send(payload) {
    const response=await fetch('http://127.0.0.1:8000/api/ingest/page',{
      method:'POST',headers:{'Content-Type':'application/json'},signal:AbortSignal.timeout(10000),
      body:JSON.stringify({...payload,captured_at:new Date().toISOString()})});
    if(!response.ok)throw Error('本地服务返回 HTTP '+response.status);
    const result=await response.json();
    if(result.ok!==true || result.detail?.ok===false)throw Error('本地服务未接受正文');
    return result;
  }
  async function tick(){
    if(inflight||Date.now()<retryAt)return;
    inflight=true;
    try{
      const detail=JobsIntelExtractor.extract();
      const cards=[...document.querySelectorAll('.job-card-box')].map(el=>({
        href:el.querySelector('a[href*="/job_detail/"]')?.getAttribute('href'),
        title_guess:text(el.querySelector('.job-name')),text:text(el),html_head:el.innerHTML||''
      }));
      const payloads=[];
      if(cards.length)payloads.push({url:location.href,page_type:'list',cards});
      if(detail.payload)payloads.push(detail.payload);
      for(const payload of payloads){
        const key=payload.page_type+'|'+payload.url, fingerprint=JSON.stringify(payload);
        if(sent.get(key)===fingerprint)continue;
        status(payload.page_type==='detail'?'正在保存正文…':'正在保存列表…');
        const result=await send(payload);
        sent.set(key,fingerprint);
        if(sent.size>100)sent.delete(sent.keys().next().value);
        console.info('[jobs-intel] 已保存',payload.page_type,result);
      }
      failures=0;retryAt=0;
      status(detail.payload ? '正文已保存 · '+detail.payload.detail.sections.join('\n').length+' 字' : (cards.length?'列表已保存 · ':'')+detail.status);
    }catch(error){
      failures++;retryAt=Date.now()+Math.min(60000,2500*2**Math.min(failures,5));
      status('未保存：'+error.message+'；将重试');console.warn('[jobs-intel]',error);
    }finally{inflight=false;}
  }
  status('等待页面内容');
  setTimeout(tick,1500);setInterval(tick,2500);
})();
