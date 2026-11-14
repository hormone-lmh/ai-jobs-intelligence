const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const script = fs.readFileSync('extension/content.js','utf8');
function harness() {
  let now = 100000, tick, body='岗位要求：熟悉 Python，具备软件开发和模型部署经验。', response={ok:true,json:async()=>({ok:true,detail:{ok:true,jd_chars:42}})};
  const badge={style:{},setAttribute(){}};
  const calls=[];
  class Clock extends Date {static now(){return now;}}
  const context={
    location:{href:'https://www.zhipin.com/job_detail/test.html',pathname:'/job_detail/test.html'},
    document:{querySelectorAll:()=>[],createElement:()=>badge,documentElement:{append(){}}},
    JobsIntelExtractor:{extract:()=>body.length<20?{status:'等待正文'}:{payload:{url:'https://www.zhipin.com/job_detail/test.html',page_type:'detail',cards:[],detail:{sections:[body]}}}},
    Date:Clock,AbortSignal,console:{info(){},warn(){}},
    setTimeout(){return 1;},clearTimeout(){},setInterval(fn){tick=fn;},
    fetch:async(url,options)=>{calls.push(JSON.parse(options.body));return response;}
  };
  vm.runInNewContext(script,context);
  return {calls,badge,tick:()=>tick(),advance(){now+=70000;},setBody(v){body=v;},setResponse(v){response=v;}};
}
test('same URL with changed JD is reported, successful duplicate is skipped',async()=>{
  const h=harness();await h.tick();await h.tick();assert.equal(h.calls.length,1);
  h.setBody('岗位要求：熟悉 Java 和 Docker，具备团队项目开发经验。');await h.tick();assert.equal(h.calls.length,2);
  assert.equal(h.calls[1].detail.body_text,undefined);
});
for(const failure of [{ok:false,status:500},{ok:true,json:async()=>({ok:false})},{ok:true,json:async()=>({ok:true,detail:{ok:false}})},{ok:true,json:async()=>{throw Error('invalid JSON');}}]) {
  test('failed HTTP or business acknowledgement retries after backoff',async()=>{
    const h=harness();h.setResponse(failure);await h.tick();await h.tick();assert.equal(h.calls.length,1);
    h.advance();h.setResponse({ok:true,json:async()=>({ok:true,detail:{ok:true,jd_chars:42}})});await h.tick();assert.equal(h.calls.length,2);
    await h.tick();assert.equal(h.calls.length,2);
  });
}
test('incomplete body waits for content',async()=>{const h=harness();h.setBody('加载中');await h.tick();assert.equal(h.calls.length,0);});

test('badge uses server character count and retains receipt on duplicate ticks',async()=>{
  const h=harness();h.setBody('  岗位要求：熟悉 Python，具备软件开发和模型部署经验。🚀\r\n  ');
  h.setResponse({ok:true,json:async()=>({ok:true,detail:{ok:true,jd_chars:37}})});
  await h.tick();assert.match(h.badge.textContent,/正文已保存 · 37 字符（含空白）/);
  await h.tick();assert.equal(h.calls.length,1);assert.match(h.badge.textContent,/37 字符/);
});

test('ignored old snapshot shows stored count without claiming it was saved',async()=>{
  const h=harness();h.setResponse({ok:true,json:async()=>({ok:true,detail:{ok:true,ignored:'older_snapshot',jd_chars:90}})});
  await h.tick();await h.tick();assert.match(h.badge.textContent,/未覆盖较新记录 · 库内 90 字符/);
  assert.doesNotMatch(h.badge.textContent,/正文已保存/);
});

test('missing character receipt is not cached as successful',async()=>{
  const h=harness();h.setResponse({ok:true,json:async()=>({ok:true,detail:{ok:true}})});
  await h.tick();assert.match(h.badge.textContent,/未保存：服务未返回已保存字数/);
  h.advance();h.setResponse({ok:true,json:async()=>({ok:true,detail:{ok:true,jd_chars:32}})});
  await h.tick();assert.equal(h.calls.length,2);assert.match(h.badge.textContent,/32 字符/);
});

test('a delayed receipt is not displayed for a changed page',async()=>{
  const h=harness();h.setResponse({ok:true,json:async()=>{
    h.setBody('另一个岗位要求：熟悉 Java 和 Docker，具备团队项目开发经验。');
    return {ok:true,detail:{ok:true,jd_chars:42}};
  }});
  await h.tick();assert.match(h.badge.textContent,/页面正文已变化/);
});

test('deleted jobs are acknowledged as skipped and not retried',async()=>{
  const h=harness();h.setResponse({ok:true,json:async()=>({ok:true,detail:{ok:true,ignored:'deleted_job',jd_chars:0}})});
  await h.tick();await h.tick();assert.equal(h.calls.length,1);
  assert.match(h.badge.textContent,/此岗位已手动删除，已跳过采集/);
  assert.doesNotMatch(h.badge.textContent,/正文已保存/);
});
