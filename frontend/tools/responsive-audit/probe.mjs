/**
 * The in-page measurement pass, as a source string evaluated via Runtime.evaluate.
 *
 * Kept as one expression rather than several round trips because a layout read is only
 * comparable if every check sees the same frame.
 */
export const PROBE = `
  const vw = window.innerWidth;
  const label = (el) => {
    const id = el.id ? '#' + el.id : '';
    const cls = typeof el.className === 'string' && el.className ? '.' + el.className.trim().split(/\\s+/).join('.') : '';
    const text = (el.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 40);
    return (el.tagName.toLowerCase() + id + cls).slice(0, 80) + (text ? ' "' + text + '"' : '');
  };
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) return false;
    const s = getComputedStyle(el);
    return s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0';
  };

  const all = Array.from(document.querySelectorAll('body *'));

  // 1. Does the page itself scroll sideways?
  const pageOverflow = Math.max(0, document.documentElement.scrollWidth - vw);

  // 2. Boxes laid out wider than the viewport — the cause of (1).
  const widerBoxes = all.filter(visible).filter((el) => el.getBoundingClientRect().width > vw + 1)
    .map((el) => ({ el: label(el), width: Math.round(el.getBoundingClientRect().width), vw }));

  // 3. Content cut off with no way to reach it: the box clips its own overflow and the
  //    content is wider than the box. overflow auto/scroll is reachable, so it is excluded.
  const clipped = all.filter(visible).filter((el) => {
    const s = getComputedStyle(el);
    const clips = s.overflowX === 'hidden' || s.overflowX === 'clip';
    return clips && el.scrollWidth > el.clientWidth + 1;
  }).map((el) => ({ el: label(el), content: el.scrollWidth, box: el.clientWidth }));

  // 4. Scrollable but with no affordance — reachable only if the user guesses to swipe.
  const hiddenScroll = all.filter(visible).filter((el) => {
    const s = getComputedStyle(el);
    return (s.overflowX === 'auto' || s.overflowX === 'scroll') && el.scrollWidth > el.clientWidth + 1;
  }).map((el) => ({ el: label(el), content: el.scrollWidth, box: el.clientWidth, offscreen: el.scrollWidth - el.clientWidth }));

  // 5. Tap targets below the 44px standard.
  const TAPPABLE = 'button, a[href], input, select, textarea, [role="button"], [tabindex]:not([tabindex="-1"])';
  const smallTargets = Array.from(document.querySelectorAll(TAPPABLE)).filter(visible).map((el) => {
    const r = el.getBoundingClientRect();
    return { el: label(el), w: Math.round(r.width), h: Math.round(r.height) };
  }).filter((t) => t.w < 44 || t.h < 44);

  // 6. Table columns collapsed to nothing — a column the user cannot reach at all.
  //    This is finding (3): @media hiding nth-child(4) deletes money columns silently.
  const zeroCells = Array.from(document.querySelectorAll('th, td')).filter((el) => {
    const s = getComputedStyle(el);
    return s.display === 'none' || el.getBoundingClientRect().width === 0;
  }).map((el) => {
    const row = el.closest('tr');
    const table = el.closest('table');
    const index = row ? Array.from(row.children).indexOf(el) : -1;
    const head = table && table.tHead && table.tHead.rows[0] ? table.tHead.rows[0].children[index] : null;
    return { column: index + 1, header: head ? (head.textContent || '').trim() : '(inconnu)' };
  });
  const hiddenColumns = [...new Map(zeroCells.map((c) => [c.column + '|' + c.header, c])).values()];

  // 7. Is the mobile drawer reachable at all? Finding (1).
  const toggle = document.querySelector('#sidebar-mobile-toggle, .sidebar-mobile-toggle');
  const sidebar = document.querySelector('.sidebar');
  // getComputedStyle(el).display is the element's OWN display and says nothing about whether an
  // ancestor is display:none — the toggle reports 'inline-block' at desktop widths purely
  // because its own rules live inside the drawer media query. getClientRects() is the question
  // actually being asked: can the user see and tap this.
  const rendered = (el) => !!el && el.getClientRects().length > 0;
  const nav = {
    toggleFound: !!toggle,
    toggleRendered: rendered(toggle),
    toggleBox: rendered(toggle) ? (() => { const r = toggle.getBoundingClientRect(); return { w: Math.round(r.width), h: Math.round(r.height) }; })() : null,
    sidebarLeft: sidebar ? Math.round(sidebar.getBoundingClientRect().left) : null,
    sidebarOnScreen: sidebar ? sidebar.getBoundingClientRect().right > 0 : null,
  };

  return {
    vw,
    matchesPhone: matchMedia('(max-width: 480px)').matches,
    matchesTablet: matchMedia('(max-width: 900px)').matches,
    pageOverflow,
    counts: {
      widerBoxes: widerBoxes.length,
      clipped: clipped.length,
      hiddenScroll: hiddenScroll.length,
      smallTargets: smallTargets.length,
      hiddenColumns: hiddenColumns.length,
    },
    widerBoxes: widerBoxes.slice(0, 12),
    clipped: clipped.slice(0, 12),
    hiddenScroll: hiddenScroll.slice(0, 12),
    smallTargets: smallTargets.slice(0, 20),
    hiddenColumns,
    nav,
  };
`;
