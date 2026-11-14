"""本地浏览器验收：独立测试数据库/原始目录，不访问外部站点。"""
from pathlib import Path
import os, subprocess, sys, time, json, socket, uuid, urllib.request, hashlib
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / 'data/test-runs' / ('ui-' + uuid.uuid4().hex)
RUN.mkdir(parents=True)
OUT = ROOT / 'output/playwright'
OUT.mkdir(parents=True, exist_ok=True)
original = ROOT / 'data/jobs.db'
before = hashlib.sha256(original.read_bytes()).hexdigest() if original.exists() else None
with socket.socket() as sock:
    sock.bind(('127.0.0.1',0))
    port=sock.getsockname()[1]
base=f'http://127.0.0.1:{port}'
env={**os.environ,'DATABASE_URL':'sqlite:///'+(RUN/'test.db').as_posix(),'JOBS_RAW_DIR':str(RUN/'raw'),'PYTHONIOENCODING':'utf-8'}
log=(RUN/'server.log').open('w',encoding='utf-8')
server=subprocess.Popen([sys.executable,'-B','-m','uvicorn','app.main:app','--host','127.0.0.1','--port',str(port)],cwd=ROOT/'backend',env=env,stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
def api(path,data=None):
    raw=json.dumps(data).encode() if data is not None else None
    req=urllib.request.Request(base+path,data=raw,headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=10) as r:return json.load(r)
try:
    for _ in range(60):
        try:api('/api/health');break
        except Exception:
            if server.poll() is not None:raise RuntimeError('Server exited: '+(RUN/'server.log').read_text())
            time.sleep(.2)
    else:raise RuntimeError('Server unavailable')
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True, channel='chrome')
        page=browser.new_page(viewport={'width':1440,'height':1100})
        errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(base)
        page.get_by_text('当前范围暂无正文技能数据。',exact=False).wait_for()
        page.screenshot(path=str(OUT/'empty-desktop.png'),full_page=True)
        cards=[{'href':f'/job_detail/qa{i}.html','title_guess':f'Python 工程师 {i}','html_head':'<span class="boss-name">测试公司</span><span class="company-location">重庆·渝北</span>'} for i in range(23)]
        cards[-1]['title_guess']='<img src=x onerror="window.injected=1">'
        cards[-1]['html_head'] = '<span class="boss-name">测试公司</span><span class="company-location">上海·浦东</span>'
        api('/api/ingest/page',{'url':'https://www.zhipin.com/web/geek/jobs','page_type':'list','cards':cards})
        page.get_by_role('button',name='刷新数据',exact=True).click()
        page.get_by_text('共 23 条 · 本页 20 条',exact=True).wait_for()
        assert page.locator('#cityOptions option').count()==2
        page.locator('#city').fill('重庆')
        page.locator('#city').press('Tab')
        page.get_by_text('共 22 条 · 本页 20 条',exact=True).wait_for()
        page.get_by_text('当前筛选：重庆；点击“全部”清除',exact=True).wait_for()
        page.get_by_role('button',name='清除城市条件：重庆',exact=True).click()
        page.get_by_text('共 23 条 · 本页 20 条',exact=True).wait_for()
        assert page.locator('#city').input_value()==''
        page.locator('#query').fill('不存在的岗位')
        page.get_by_role('button',name='应用筛选',exact=True).click()
        page.get_by_text('共 0 条 · 本页 0 条',exact=True).wait_for()
        page.get_by_role('button',name='重置筛选',exact=True).click()
        page.get_by_text('共 23 条 · 本页 20 条',exact=True).wait_for()
        assert page.locator('#activeFilters button').count()==0
        page.locator('#city').fill('上海')
        page.locator('#city').press('Tab')
        page.get_by_text('共 1 条 · 本页 1 条',exact=True).wait_for()
        page.get_by_role('button',name='清除城市筛选').click()
        page.get_by_text('共 23 条 · 本页 20 条',exact=True).wait_for()
        assert page.locator('#jobs img').count()==0
        assert page.evaluate('window.injected') is None
        page.get_by_role('button',name='下一页',exact=True).click()
        page.get_by_text('共 23 条 · 本页 3 条',exact=True).wait_for()
        page.locator('#jdUrl').fill('https://www.zhipin.com/job_detail/qa0.html')
        page.locator('#jdText').fill('岗位职责：使用 Python 与 PyTorch 进行模型训练，负责上线部署和性能评估。')
        page.get_by_role('button',name='保存并重新分析').click()
        page.get_by_text('已保存，正文技能已重新分析。',exact=True).wait_for()
        page.locator('#source').select_option('jd')
        page.locator('#heatGrid button').filter(has_text='PyTorch').wait_for()
        assert page.locator('#heatGrid button').filter(has_text='PyTorch').get_attribute('aria-label').startswith('PyTorch：1 个岗位')
        page.locator('#heatGrid button').filter(has_text='PyTorch').click()
        page.get_by_text('共 1 条 · 本页 1 条',exact=True).wait_for()
        page.locator('#heatGrid button').filter(has_text='PyTorch').click()
        page.locator('#skills button').filter(has_text='PyTorch').click()
        page.get_by_text('共 1 条 · 本页 1 条',exact=True).wait_for()
        page.get_by_role('button',name='查看正文与技能依据').click()
        page.locator('#detailBody').filter(has_text='使用 Python 与 PyTorch').wait_for()
        assert '正文' in page.locator('#evidence').inner_text()
        page.screenshot(path=str(OUT/'detail-desktop.png'),full_page=True)
        page.get_by_role('button',name='关闭详情',exact=True).click()
        page.locator('#jdText').fill('岗位要求：使用 Java 和 Docker 完成业务系统开发、部署和日常维护。')
        page.get_by_role('button',name='保存并重新分析').click()
        page.get_by_text('已保存，正文技能已重新分析。',exact=True).wait_for()
        page.wait_for_function("!document.querySelector('#saveJd').disabled")
        result=api('/api/stats/skills?source=jd')
        assert 'PyTorch' not in [r['skill'] for r in result['items']]
        page.get_by_role('button',name='清除技能筛选').click()
        page.get_by_text('共 23 条 · 本页 20 条',exact=True).wait_for()
        # New ingestion must update counts via the timer without a manual refresh.
        api('/api/import/jd',{'url':'https://www.zhipin.com/job_detail/qa1.html','jd_text':'岗位要求：熟练使用 Java 和 Docker 完成开发、部署及线上系统维护。'})
        page.wait_for_function("document.querySelector('[data-heat-skill=Java] strong')?.textContent==='2'",timeout=40000)
        page.locator('#heatAuto').uncheck()
        page.get_by_text('自动更新已暂停',exact=False).wait_for()
        page.route('**/api/stats/skills?*',lambda route:route.abort())
        page.locator('#heatAuto').check()
        page.locator('#heatStatus').filter(has_text='同步失败').wait_for()
        assert page.locator('[data-heat-skill=Java] strong').inner_text()=='2'
        page.unroute('**/api/stats/skills?*')
        page.locator('#heatAuto').uncheck()
        page.locator('#heatAuto').check()
        page.locator('#heatStatus').filter(has_text='最近同步').wait_for()
        page.locator('#heatGrid').screenshot(path=str(OUT/'heatmap.png'))
        page.evaluate('window.scrollTo(0,0)')
        page.screenshot(path=str(OUT/'dashboard-preview.png'))
        page.screenshot(path=str(OUT/'dashboard-desktop.png'),full_page=True)
        page.set_viewport_size({'width':390,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.screenshot(path=str(OUT/'dashboard-mobile.png'),full_page=True)
        page.set_viewport_size({'width':1440,'height':1100})
        page.get_by_role('button',name='招聘公司',exact=True).click()
        page.get_by_text('共 1 家公司；',exact=False).wait_for()
        page.screenshot(path=str(OUT/'companies-desktop.png'),full_page=True)
        page.locator('#openImport').click()
        assert page.locator('#view-explore').is_visible()
        assert page.locator('#jdUrl').evaluate('(el)=>el===document.activeElement')
        page.get_by_role('button',name='招聘公司',exact=True).click()
        page.get_by_text('共 1 家公司；',exact=False).wait_for()
        page.get_by_role('button',name='查看该公司岗位').click()
        page.get_by_text('共 23 条 · 本页 20 条',exact=True).wait_for()
        assert page.locator('#company').input_value()=='测试公司'
        page.get_by_role('button',name='需求对比',exact=True).click()
        page.locator('#leftCity').fill('重庆')
        page.locator('#rightCity').fill('深圳')
        page.get_by_role('button',name='分析两组需求').click()
        page.get_by_text('分析完成 ·',exact=False).wait_for()
        assert '不可比较' in page.locator('#compareResults').inner_text()
        page.screenshot(path=str(OUT/'comparison-desktop.png'),full_page=True)
        page.set_viewport_size({'width':390,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.screenshot(path=str(OUT/'comparison-mobile.png'),full_page=True)
        page.get_by_role('button',name='岗位与技能',exact=True).click()
        page.locator('#resetFilters').click()
        page.get_by_text('共 23 条 · 本页 20 条',exact=True).wait_for()
        page.once('dialog',lambda dialog:dialog.dismiss())
        page.locator('#jobs .deleteJob').first.click()
        assert api('/api/stats/overview')['jobs']==23
        # Failure leaves records and controls intact.
        page.route('**/api/jobs/qa*',lambda route:route.abort() if route.request.method=='DELETE' else route.continue_())
        page.once('dialog',lambda dialog:dialog.accept())
        page.locator('#jobs .deleteJob').first.click()
        page.locator('#deleteStatus').filter(has_text='删除未确认成功').wait_for()
        assert api('/api/stats/overview')['jobs']==23
        page.unroute('**/api/jobs/qa*')
        page.locator('#query').fill('Python 工程师 0')
        page.locator('#search').click()
        page.get_by_text('共 1 条 · 本页 1 条',exact=True).wait_for()
        page.get_by_role('button',name='查看正文与技能依据').click()
        page.locator('#detailMeta .deleteJob').wait_for()
        page.once('dialog',lambda dialog:dialog.accept())
        page.locator('#detailMeta .deleteJob').click()
        page.get_by_text('共 0 条 · 本页 0 条',exact=True).wait_for()
        assert not page.locator('#detailDialog').is_visible()
        assert api('/api/stats/overview')['jobs']==22
        result=api('/api/ingest/page',{'url':'https://www.zhipin.com/web/geek/jobs','page_type':'list','cards':[cards[0]]})
        assert result['skipped']==1 and api('/api/stats/overview')['jobs']==22
        page.locator('#resetFilters').click()
        page.get_by_text('共 22 条 · 本页 20 条',exact=True).wait_for()
        assert page.locator('[data-heat-skill=Java] strong').inner_text()=='1'
        page.screenshot(path=str(OUT/'delete-result-mobile.png'),full_page=True)
        assert not errors,errors
        browser.close()
    assert before == (hashlib.sha256(original.read_bytes()).hexdigest() if original.exists() else None)
    print(json.dumps({'ok':True,'checks':['empty state','23-job pagination','safe text rendering','manual JD entry','skill filtering','detail evidence','JD replacement','mobile overflow','filter chips','reset filters','header import shortcut','company drilldown','comparison','no JS errors','real database unchanged'],'artifacts':str(OUT)},ensure_ascii=False))
finally:
    server.terminate()
    try:server.wait(timeout=8)
    except subprocess.TimeoutExpired:server.kill();server.wait()
    log.close()
