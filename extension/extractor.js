// 只从可见职位描述区提取正文，用面板内详情链接绑定岗位。
(function () {
  const text = el => (el?.innerText || el?.textContent || '').trim();
  const visible = el => !!el && el.getClientRects().length > 0 && getComputedStyle(el).visibility !== 'hidden';
  function jobUrl(value) {
    try {
      const u = new URL(value, location.href);
      const match = u.pathname.match(/^\/job_detail\/([\w-]+)\.html$/);
      return u.origin === 'https://www.zhipin.com' && match ? u.origin + u.pathname : null;
    } catch { return null; }
  }
  function extract() {
    const direct = jobUrl(location.href);
    const more = [...document.querySelectorAll('a[href*="/job_detail/"]')]
      .filter(el => visible(el) && /查看更多信息|查看职位详情|查看完整职位/.test(text(el)));
    // 列表页必须有唯一面板身份；不能拿列表第一条或刚点击的卡片猜测。
    const targets = [...new Set(more.map(el => jobUrl(el.href)).filter(Boolean))];
    const url = direct || (targets.length === 1 ? targets[0] : null);
    if (!url) return {status:'等待打开具体岗位详情'};
    let scope = document;
    if (!direct) {
      let root = more.find(el => jobUrl(el.href) === url).parentElement;
      while (root && root !== document.body) {
        if ([...root.querySelectorAll('h1,h2,h3,h4,h5')].some(el => visible(el) && /^(职位描述|岗位职责|任职要求|职位要求|工作职责)[：:]?$/.test(text(el)))) {scope = root;break;}
        root = root.parentElement;
      }
      if (scope === document) return {status:'已识别岗位，等待描述面板加载'};
    }
    const headingPattern = /^(职位描述|岗位职责|任职要求|职位要求|工作职责)[：:]?$/;
    const headings = [...scope.querySelectorAll('h1,h2,h3,h4,h5')].filter(el => visible(el) && headingPattern.test(text(el)));
    let sections = [];
    for (const heading of headings) {
      // 常见结构：h3 后紧邻正文容器。不读取整页面/整个详情面板。
      let sibling = heading.nextElementSibling;
      while (sibling) {
        if (/^H[1-6]$/.test(sibling.tagName) || sibling.querySelector('h1,h2,h3,h4,h5')) break;
        const value = text(sibling);
        if (visible(sibling) && value.length >= 20) {sections.push(value);break;}
        sibling = sibling.nextElementSibling;
      }
    }
    if (!sections.length) {
      sections = [...scope.querySelectorAll('.job-sec-text, .job-detail-body .desc')]
        .filter(el => visible(el) && !el.closest('.job-card-box'))
        .filter(el => {
          const parent = el.closest('.job-sec, .job-detail-section');
          const label = text(parent?.querySelector('h3, .title'));
          return !label || headingPattern.test(label);
        }).map(text).filter(s => s.length >= 20);
    }
    sections = [...new Set(sections)];
    if (!sections.length) return {status:'未识别到职位正文，请展开详情后重试'};
    return {payload:{url, page_type:'detail', cards:[], detail:{sections,headings:headings.map(text)}},status:'已识别正文'};
  }
  globalThis.JobsIntelExtractor = {extract, jobUrl};
})();
