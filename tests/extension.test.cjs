const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const script = fs.readFileSync('extension/content.js','utf8');
function harness() {
  let now = 100000, tick, body='岗位要求：熟悉 Python，具备软件开发和模型部署经验。', response={ok:true,json:async()=>({ok:true,detail:{ok:true}})};
  const calls=[];
  class Clock extends Date {static now(){return now;}}
  const context={
    location:{href:'https://www.zhipin.com/job_detail/test.html',pathname:'/job_detail/test.html'},
    document:{querySelectorAll:()=>[],createElement:()=>({style:{},setAttribute(){}}),documentElement:{append(){}}},
    JobsIntelExtractor:{extract:()=>body.length<20?{status:'等待正文'}:{payload:{url:'https://www.zhipin.com/job_detail/test.html',page_type:'detail',cards:[],detail:{sections:[body]}}}},
    Date:Clock,AbortSignal,console:{info(){},warn(){}},
    setTimeout(){return 1;},clearTimeout(){},setInterval(fn){tick=fn;},
    fetch:async(url,options)=>{calls.push(JSON.parse(options.body));return response;}
  };
  vm.runInNewContext(script,context);
  return {calls,tick:()=>tick(),advance(){now+=70000;},setBody(v){body=v;},setResponse(v){response=v;}};
}
test('same URL with changed JD is reported, successful duplicate is skipped',async()=>{
  const h=harness();await h.tick();await h.tick();assert.equal(h.calls.length,1);
  h.setBody('岗位要求：熟悉 Java 和 Docker，具备团队项目开发经验。');await h.tick();assert.equal(h.calls.length,2);
  assert.equal(h.calls[1].detail.body_text,undefined);
});
for(const failure of [{ok:false,status:500},{ok:true,json:async()=>({ok:false})},{ok:true,json:async()=>({ok:true,detail:{ok:false}})},{ok:true,json:async()=>{throw Error('invalid JSON');}}]) {
  test('failed HTTP or business acknowledgement retries after backoff',async()=>{
    const h=harness();h.setResponse(failure);await h.tick();await h.tick();assert.equal(h.calls.length,1);
    h.advance();h.setResponse({ok:true,json:async()=>({ok:true})});await h.tick();assert.equal(h.calls.length,2);
    await h.tick();assert.equal(h.calls.length,2);
  });
}
test('incomplete body waits for content',async()=>{const h=harness();h.setBody('加载中');await h.tick();assert.equal(h.calls.length,0);});
