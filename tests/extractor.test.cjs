const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const source=fs.readFileSync('extension/extractor.js','utf8');
function fixture({direct=false,ambiguous=false,hidden=false,body='岗位职责：负责 Python 和模型部署，要求相关实习经验。'}={}){
 const content={innerText:body,tagName:'DIV',querySelector:()=>null,getClientRects:()=>[{}]};
 const heading={innerText:'职位描述',nextElementSibling:content,getClientRects:()=>[{}]};
 const panel={querySelectorAll:selector=>selector.includes('h1')?[heading]:[],parentElement:null};
 const link={innerText:'查看更多信息',href:'https://www.zhipin.com/job_detail/target.html?securityId=private',parentElement:panel,getClientRects:()=>hidden?[]:[{}]};
 const links=[link];if(ambiguous)links.push({...link,href:'https://www.zhipin.com/job_detail/other.html'});
 const document={body:{},querySelectorAll:selector=>selector.startsWith('a[')?links:selector.includes('h1')?[heading]:[]};
 const ctx={document,location:{href:direct?'https://www.zhipin.com/job_detail/direct.html':'https://www.zhipin.com/web/geek/jobs'},URL,getComputedStyle:()=>({visibility:'visible'})};
 vm.runInNewContext(source,ctx);return ctx.JobsIntelExtractor.extract();
}
test('list page panel is bound to its more-info URL, query secrets stripped',()=>{
 const r=fixture();assert.equal(r.payload.url,'https://www.zhipin.com/job_detail/target.html');assert.match(r.payload.detail.sections[0],/Python/);
});
test('standalone detail works',()=>assert.equal(fixture({direct:true}).payload.url,'https://www.zhipin.com/job_detail/direct.html'));
test('ambiguous or hidden panel is not assigned to an arbitrary list card',()=>{
 assert.equal(fixture({ambiguous:true}).payload,undefined);assert.equal(fixture({hidden:true}).payload,undefined);
});
test('loading body is not uploaded as JD',()=>assert.equal(fixture({body:'加载中'}).payload,undefined));
