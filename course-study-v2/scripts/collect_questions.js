/* Pure read-only collector for an already-open, authorized question document.
 * Pass the document and options through the supported browser execution API. */
(function collect(document, options = {}) {
  options = options || {};
  const doc = document;
  const warnings = [];
  const fonts = [];
  const familyToId = new Map();
  const cleanFamily = value => String(value || '').trim().replace(/^['"]|['"]$/g, '').toLowerCase();
  for (const style of doc.querySelectorAll('style')) {
    for (const face of String(style.textContent || '').matchAll(/@font-face\s*\{([^}]+)\}/gi)) {
      const family = /font-family\s*:\s*([^;]+)/i.exec(face[1]);
      const data = /url\(\s*['"]?data:[^,]+;base64,([a-z0-9+/=\s]+)['"]?\s*\)/i.exec(face[1]);
      if (!family || !data) continue;
      const key = cleanFamily(family[1]);
      if (familyToId.has(key)) continue;
      const id = 'embedded-' + (fonts.length + 1);
      familyToId.set(key, id);
      fonts.push({ id, family: key, data_base64: data[1].replace(/\s/g, '') });
    }
  }

  let view = null;
  try { view = doc.defaultView; } catch {
    warnings.push('Document style view unavailable: font identity and visibility require visual review.');
  }
  function styleFor(element) {
    try {
      if (view && typeof view.getComputedStyle === 'function') return view.getComputedStyle(element);
    } catch { /* The current harness may expose DOM without computed styles. */ }
    warnings.push('Computed style unavailable: font identity and visibility require visual review.');
    return null;
  }
  function runsFor(root, excluded = new Set()) {
    const runs = [];
    function add(text, font, unresolved = false, warning = null) {
      if (!text) return;
      const previous = runs[runs.length - 1];
      if (previous && previous.font === font && !!previous.font_unresolved === unresolved &&
          (previous.warnings || []).join() === (warning || '')) previous.text += text;
      else runs.push({ text, font, ...(unresolved ? {
        font_unresolved: true, needs_review: true, warnings: [warning],
      } : {}) });
    }
    function walk(node, parent) {
      if (excluded.has(node)) return;
      if (node.nodeType === 3) {
        const css = styleFor(parent || node.parentElement);
        const families = String(css && css.fontFamily || '').split(',').map(cleanFamily);
        const embedded = families.find(family => familyToId.has(family));
        const fontReadable = css && typeof css.fontFamily === 'string' && css.fontFamily.trim();
        const warning = !fontReadable ? 'Computed font unavailable; captured text is not verified plaintext.' :
          !embedded && families.some(family => /secret|obfus|cxfont/.test(family)) ?
            'Font not embedded/readable: ' + families.join(',') : null;
        if (warning) warnings.push(warning);
        add(node.nodeValue || '', embedded ? familyToId.get(embedded) : 'normal', !!warning, warning);
        return;
      }
      if (node.nodeType !== 1) return;
      if (/^(SCRIPT|STYLE|INPUT|TEXTAREA|SELECT|BUTTON)$/.test(node.tagName || '')) return;
      const css = styleFor(node);
      if (css && (css.display === 'none' || css.visibility === 'hidden')) return;
      if (node.tagName === 'BR') { add('\n', 'normal'); return; }
      for (const child of node.childNodes || []) walk(child, node);
      if (/^(P|DIV)$/.test(node.tagName || '')) add('\n', 'normal');
    }
    walk(root, root);
    return runs;
  }

  const questionNodes = Array.from(doc.querySelectorAll(options.question_selector || '.TiMu'));
  if (!questionNodes.length) throw new Error('NO_QUESTIONS: confirm the current question frame; no whole-page fallback');
  const questions = questionNodes.map((question, index) => {
    const rows = Array.from(question.querySelectorAll(options.option_selector || 'li')).filter(row =>
      options.option_selector || /addChoice|addMultipleChoice/.test(row.getAttribute('onclick') || '') ||
      row.querySelector('.num_option_dx, .num_option, input[type="radio"], input[type="checkbox"]'));
    const uniqueRows = rows.filter((row, i) => rows.indexOf(row) === i && !rows.some(other => other !== row && other.contains(row)));
    const stemNode = question.querySelector(options.stem_selector || '.Zy_TItle, .questionTitle, .mark_name');
    const stem = runsFor(stemNode || question, new Set(uniqueRows));
    const choices = uniqueRows.map((row, optionIndex) => {
      const labelNode = row.querySelector(options.option_label_selector || '.num_option_dx, .num_option');
      const visibleLabel = labelNode ? String(labelNode.textContent || '').trim() : '';
      const label = visibleLabel || String.fromCharCode(65 + optionIndex);
      return { label, label_inferred: !visibleLabel, runs: runsFor(row, new Set(labelNode ? [labelNode] : [])) };
    });
    const images = Array.from(question.querySelectorAll('img')).map((img, imageIndex) => {
      const choiceIndex = uniqueRows.findIndex(row => row.contains(img));
      return {
        src: img.currentSrc || img.src || '', caption: img.alt || '', requires_visual_review: true,
        role: choiceIndex >= 0 ? 'option' : 'stem', image_index: imageIndex,
        ...(choiceIndex >= 0 ? { option_label: choices[choiceIndex].label } : {}),
      };
    });
    const id = question.getAttribute('data-qid') || question.id || `q${index + 1}`;
    return { id, stem, options: choices, images, needs_review: true };
  });

  const usedFonts = new Set(questions.flatMap(question => [
    ...question.stem.map(run => run.font), ...question.options.flatMap(choice => choice.runs.map(run => run.font)),
  ]));
  let pagePath = '';
  try { pagePath = new URL(doc.URL || doc.documentURI || '').pathname; } catch { /* Optional DOM URL. */ }
  return {
    schema_version: 1,
    batch_id: options.batch_id || ('batch-' + Date.now() + '-' + Math.random().toString(36).slice(2, 8)),
    source: { platform: 'chaoxing', page_path: pagePath, ...(options.source || {}) },
    fonts: fonts.filter(font => usedFonts.has(font.id)), questions,
    warnings: [...new Set(warnings)],
    captured_at: new Date().toISOString(),
  };
})
