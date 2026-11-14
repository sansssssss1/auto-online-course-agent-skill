/* Pure read-only collector. Pass the actual list document and options explicitly. */
(function collect(document, options = {}) {
  const opts = options || {};
  const platform = opts.platform || 'chaoxing';
  const scope = opts.scope || {};
  const view = scope.view || 'homework';
  const text = element => String(element && (element.innerText || element.textContent) || '').trim().replace(/\s+/g, ' ');
  const selectors = opts.item_selector ? [opts.item_selector] : platform === 'icourse163'
    ? [view === 'content' ? '.sourceList .lsicon' : '.u-quizHwListItem']
    : view === 'content' ? ['.catalog_title[role="link"]', '.posCatalog_select', '.chapter_item']
      : ['li[onclick*="goTask"]'];
  let nodes = [];
  for (const selector of selectors) {
    nodes = Array.from(document.querySelectorAll(selector));
    if (nodes.length) break;
  }
  function statusFor(node, label) {
    if (node.classList && node.classList.contains('learned')) return 'completed';
    if (node.querySelector && node.querySelector('.icon_Completed, .ans-job-finished, .icon_yiwanc')) return 'completed';
    if (/待批阅|待评分|已提交/.test(label)) return 'submitted';
    if (/待互评|互评中/.test(label)) return 'awaiting-peer-review';
    if (/未交|未提交|待完成|未完成/.test(label)) return 'pending';
    if (/已完成|已批阅/.test(label)) return 'completed';
    return 'unknown';
  }
  const items = nodes.map((node, index) => {
    const titleNode = node.querySelector && node.querySelector(opts.title_selector || '.j-name, h3, h4, .posCatalog_name, .chapter_name, a.clicktitle');
    const label = text(node);
    const title = text(titleNode) || label;
    const raw = node.getAttribute('data') || node.getAttribute('data-cid') || node.getAttribute('data-id') || '';
    let id = node.getAttribute('data-cid') || node.getAttribute('data-id') || node.id || '';
    if (!id && view === 'content' && node.getAttribute('role') === 'link') {
      const labelledBy = node.getAttribute('aria-labelledby') || '';
      if (/^tab_cur\d+$/.test(labelledBy)) id = labelledBy;
    }
    if (!id && /^https?:/.test(raw)) {
      try {
        const url = new URL(raw.replace(/&amp;/g, '&'));
        for (const key of ['workId', 'workid', 'taskId', 'taskid', 'knowledgeid', 'id']) {
          if (url.searchParams.get(key)) { id = key + ':' + url.searchParams.get(key); break; }
        }
      } catch {}
    }
    const deadlineNode = node.querySelector && node.querySelector(opts.deadline_selector || '.deadline, .endTime, .time');
    return {
      id: id || ('title:' + title), id_inferred: !id,
      title, kind: view === 'content' ? 'content' : view === 'quiz' ? 'quiz' : 'homework',
      status: statusFor(node, label), deadline: text(deadlineNode) || null,
      observed_text: label, row_index: index,
    };
  });
  return {
    schema_version: 1, platform,
    scope: { account_alias: scope.account_alias || '', course_key: scope.course_key || '', view },
    captured_at: new Date().toISOString(),
    authoritative: items.length > 0 && opts.loaded_scope_confirmed === true,
    items,
    warnings: [
      ...(!items.length ? ['No parsed items is not proof of an empty task list.'] : []),
      ...(opts.loaded_scope_confirmed !== true ? ['Loaded range/pagination must be confirmed by the supervisor.'] : []),
      ...(!scope.account_alias || !scope.course_key ? ['Set task scope before comparing snapshots.'] : []),
    ],
  };
})
