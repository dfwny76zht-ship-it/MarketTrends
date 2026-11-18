/* Investor page: everything is computed from data.json (frozen snapshot of 18.11.2026). */
(async function () {
  const data = await (await fetch('data.json', { cache: 'no-store' })).json();
  const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  const $ = (id) => document.getElementById(id);
  const nf0 = new Intl.NumberFormat('de-DE', { maximumFractionDigits: 0 });
  const eur = (v) => (v == null ? '–' : v.toLocaleString('de-DE', { style: 'currency', currency: 'EUR' }));
  const eur0 = (v) => v.toLocaleString('de-DE', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 });
  const pct = (v) => `${nf0.format(v * 100)} %`;
  const median = (xs) => {
    const s = xs.filter((x) => x != null).sort((a, b) => a - b);
    if (!s.length) return null;
    const m = s.length >> 1;
    return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
  };
  const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);

  // ---------- groups ----------
  const NAMES = [
    [/^carnosa/i, 'Carnosa-artig', 'Carnosa-artig (Sorten, Hybriden, nahe Verwandte)', '--c1'],
    [/^kerrii/i, 'Kerrii-artig', 'Kerrii-artig', '--c2'],
    [/^wayet/i, 'Wayettii-artig', 'Wayettii-artig', '--c3'],
  ];
  const groups = {}; // id -> {id, name, long, color, parent}
  const tops = [];
  for (const g of data.groups.filter((x) => !x.parent)) {
    const m = NAMES.find(([re]) => re.test(g.label)) ?? [null, g.label, g.label, '--other'];
    groups[g.id] = { id: g.id, name: m[1], long: m[2], color: css(m[3]), parent: null };
    tops.push(g.id);
  }
  groups.other = { id: 'other', name: 'Übrige Arten', long: 'Übrige Arten', color: css('--other'), parent: null };
  tops.push('other');
  for (const g of data.groups.filter((x) => x.parent)) {
    const name = /single leaf/i.test(g.label) ? 'Einzelblatt ohne Knoten' : g.label;
    groups[g.id] = { id: g.id, name, long: `${groups[g.parent].name} › ${name}`, color: shade(groups[g.parent].color, 0.35), parent: g.parent };
  }
  const subsOf = (id) => Object.values(groups).filter((g) => g.parent === id);
  const topOf = (o) => (o.group == null ? 'other' : groups[o.group]?.parent ?? o.group);
  const inGroup = (o, id) => (groups[id]?.parent ? o.group === id : topOf(o) === id);

  function shade(hex, amount) {
    const n = parseInt(hex.replace('#', ''), 16);
    const c = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((v) => Math.round(v * (1 - amount)));
    return `#${c.map((v) => v.toString(16).padStart(2, '0')).join('')}`;
  }

  const FA = data.offers.filter((o) => o.shop === 'FlorAccess');
  const BJ = data.offers.filter((o) => o.shop === "Ben's Jungle");
  const value = (o) => (o.stock ?? 0) * (o.net ?? 0);
  const sum = (xs, f) => xs.reduce((s, x) => s + f(x), 0);
  const species = (xs) => new Set(xs.map((o) => o.species_key)).size;

  // ---------- lead and tiles ----------
  const stockAll = sum(FA, (o) => o.stock ?? 0);
  const valueAll = sum(FA, value);
  const isCK = (o) => { const t = topOf(o); return t !== 'other' && /^(Carnosa|Kerrii)/.test(groups[t].name); };
  const ckStock = sum(FA.filter(isCK), (o) => o.stock ?? 0) / stockAll;
  const ckValue = sum(FA.filter(isCK), value) / valueAll;
  $('lead').innerHTML = `Beim niederländischen Großhändler FlorAccess sind <strong>${pct(ckStock)} der Pflanzen im Bestand
    und ${pct(ckValue)} des Lagerwerts Carnosa- oder Kerrii-artig</strong>. Hinter ${species(FA)} Arten und
    ${FA.length} Angeboten steckt also ein schmales Sortiment.`;

  const tile = (l, v, r = '') => `<div class="tile"><div class="l">${l}</div><div class="v">${v}</div>${r ? `<div class="r">${r}</div>` : ''}</div>`;
  const bjr = (v) => `<span class="retail-only">Ben's Jungle: ${v}</span>`;
  $('tiles').innerHTML =
    tile('Arten', species(FA), bjr(species(BJ))) +
    tile('Angebote', FA.length, bjr(BJ.length)) +
    tile('Pflanzen im Bestand', nf0.format(stockAll), bjr('nicht veröffentlicht')) +
    tile('Lagerwert (netto)', eur0(valueAll), bjr('–')) +
    tile('Medianpreis', eur(median(FA.map((o) => o.net))) + '<small style="font-size:12px;font-weight:400"> netto</small>',
      bjr(`${eur(median(BJ.map((o) => o.price)))} inkl. MwSt.`));

  // ---------- donuts ----------
  const charts = {};
  let selected = null;

  function donut(el, offers, measure, unit) {
    const chart = echarts.init(el, null, { renderer: 'svg' });
    const draw = () => {
      const val = (xs) => sum(xs, measure);
      const total = val(offers) || 1;
      const outer = tops.map((id) => ({ id, v: val(offers.filter((o) => topOf(o) === id)) })).filter((p) => p.v > 0);
      const inner = [];
      const arrows = [];
      let acc = 0;
      for (const p of outer) {
        for (const sg of subsOf(p.id)) {
          const v = val(offers.filter((o) => o.group === sg.id));
          if (!v) continue;
          inner.push({ name: sg.long, value: v, gid: sg.id, parentV: p.v, parentName: groups[p.id].name,
            itemStyle: { color: sg.color, borderColor: '#fff', borderWidth: 2 } });
          arrows.push({ mid: (acc + v / 2) / total, share: v / total, index: inner.length - 1 });
          acc += v;
          p.rest = (p.rest ?? p.v) - v;
        }
        const rest = p.rest ?? p.v;
        if (rest > 0) inner.push({ name: '', value: rest, itemStyle: { color: 'transparent' }, tooltip: { show: false }, emphasis: { disabled: true } });
        acc += rest;
      }
      const w = chart.getWidth();
      const h = chart.getHeight();
      const R = Math.min(w, h) / 2;
      const [r0, r1] = [44, 76];
      const at = (frac, r) => {
        const a = ((90 - 360 * frac) * Math.PI) / 180;
        return [w / 2 + r * R * Math.cos(a), h / 2 - r * R * Math.sin(a)];
      };
      const graphic = arrows.map((ar) => {
        const tail = at(ar.mid, (r0 - 24) / 100);
        const tip = at(ar.mid, (r0 - 2) / 100);
        const a = Math.atan2(tip[1] - tail[1], tip[0] - tail[0]);
        const left = [tip[0] - 7 * Math.cos(a - 0.45), tip[1] - 7 * Math.sin(a - 0.45)];
        const right = [tip[0] - 7 * Math.cos(a + 0.45), tip[1] - 7 * Math.sin(a + 0.45)];
        const ink = css('--ink-2');
        return {
          type: 'group',
          onmouseover: () => chart.dispatchAction({ type: 'showTip', seriesIndex: 1, dataIndex: ar.index }),
          onmouseout: () => chart.dispatchAction({ type: 'hideTip' }),
          onclick: () => showGroup(inner[ar.index].gid),
          children: [
            { type: 'line', shape: { x1: tail[0], y1: tail[1], x2: tip[0], y2: tip[1] }, style: { stroke: ink, lineWidth: 1.5 } },
            { type: 'polygon', shape: { points: [tip, left, right] }, style: { fill: ink } },
            { type: 'text', x: tail[0], y: tail[1], style: { text: pct(ar.share), fill: ink, font: '600 12px system-ui, sans-serif',
              align: 'center', verticalAlign: 'middle', backgroundColor: '#fff', padding: [1, 3] } },
          ],
        };
      });
      const fmt = (v) => (unit === '€' ? eur0(v) : `${nf0.format(v)} ${unit}`);
      chart.setOption({
        animation: false,
        textStyle: { fontFamily: 'system-ui, sans-serif' },
        tooltip: {
          trigger: 'item', backgroundColor: '#fff', borderColor: css('--line'), textStyle: { color: css('--ink'), fontSize: 13 },
          formatter: (p) => p.seriesIndex === 1
            ? `${p.marker}<b>${esc(p.data.name)}</b><br>${fmt(p.value)} · ${p.percent} % des Ganzen · ${nf0.format((p.value / p.data.parentV) * 100)} % von ${esc(p.data.parentName)}`
            : `${p.marker}<b>${esc(groups[p.data.gid].long)}</b><br>${fmt(p.value)} · ${p.percent} %`,
        },
        graphic,
        series: [
          { type: 'pie', radius: [`${r0}%`, `${r1}%`], center: ['50%', '50%'], label: { show: true, position: 'inside',
              formatter: (p) => (p.percent >= 6 ? `${Math.round(p.percent)} %` : ''), color: '#fff', fontSize: 12, fontWeight: 600 },
            itemStyle: { borderColor: '#fff', borderWidth: 2, borderRadius: 4 }, emphasis: { scale: false },
            data: outer.map((p) => ({ name: groups[p.id].name, value: p.v, gid: p.id,
              itemStyle: { color: groups[p.id].color, opacity: !selected || selected === p.id || groups[selected]?.parent === p.id ? 1 : 0.35 } })) },
          { type: 'pie', radius: [`${r0}%`, `${r0 + 0.6 * (r1 - r0)}%`], center: ['50%', '50%'], label: { show: false },
            labelLine: { show: false }, emphasis: { scale: false }, data: inner },
        ],
      }, true);
    };
    chart.on('click', (p) => p.data?.gid != null && showGroup(p.data.gid));
    new ResizeObserver(() => { chart.resize(); draw(); }).observe(el);
    draw();
    return { chart, draw };
  }

  charts.stock = donut($('c-stock'), FA, (o) => o.stock ?? 0, 'Pflanzen');
  charts.value = donut($('c-value'), FA, value, '€');
  charts.retail = donut($('c-retail'), BJ, () => 1, 'Angebote');

  const kerriiId = tops.find((id) => groups[id].name === 'Kerrii-artig');
  const carnosaId = tops.find((id) => groups[id].name === 'Carnosa-artig');
  const share = (id, f) => sum(FA.filter((o) => topOf(o) === id), f);
  $('caption').textContent = `Kerrii-artige sind ${pct(share(kerriiId, (o) => o.stock ?? 0) / stockAll)} der Pflanzen, aber nur ${pct(share(kerriiId, value) / valueAll)} des Lagerwerts – überwiegend günstige Einzelblätter.`;

  // ---------- legend and group lists ----------
  function legend() {
    const items = tops.flatMap((id) => [id, ...subsOf(id).map((s) => s.id)]);
    $('legend').innerHTML = items.map((id) => {
      const g = groups[id];
      return `<button data-g="${id}" class="${selected == id ? 'on' : ''}"><span class="sw${g.parent ? ' hollow' : ''}" style="${g.parent ? `border-color:${g.color}` : `background:${g.color}`}"></span>${esc(g.parent ? '└ ' + g.name : g.name)}</button>`;
    }).join('');
    for (const b of $('legend').querySelectorAll('button')) b.onclick = () => showGroup(b.dataset.g === 'other' ? 'other' : Number(b.dataset.g));
  }

  function showGroup(id) {
    selected = selected == id ? null : id;
    Object.values(charts).forEach((c) => c.draw());
    legend();
    const box = $('grouplist');
    if (selected == null) { box.hidden = true; return; }
    const g = groups[selected];
    const fa = FA.filter((o) => inGroup(o, selected)).sort((a, b) => (b.stock ?? 0) - (a.stock ?? 0));
    const bj = BJ.filter((o) => inGroup(o, selected)).sort((a, b) => a.price - b.price);
    box.hidden = false;
    box.innerHTML = `
      <div class="gl-head"><h3>${esc(g.long)}: ${fa.length} Angebote bei FlorAccess, ${nf0.format(sum(fa, (o) => o.stock ?? 0))} Pflanzen, ${eur0(sum(fa, value))}</h3>
        <button onclick="this.closest('.grouplist').hidden = true">Schließen</button></div>
      <div class="scroll"><table>
        <tr><th>Angebot</th><th>Art / Sorte</th><th>Topf / Höhe</th><th class="n">Preis netto</th><th class="n">Bestand</th><th class="n">Lagerwert</th></tr>
        ${fa.map((o) => `<tr><td>${esc(o.name)}</td><td><em>${esc(o.plant)}</em></td><td>${esc(o.pot ?? '')} / ${esc(o.height ?? '')}</td>
          <td class="n">${eur(o.net)}</td><td class="n">${o.stock != null ? nf0.format(o.stock) : '–'}</td><td class="n">${eur0(value(o))}</td></tr>`).join('')}
      </table></div>
      <div class="retail-only" style="margin-top:8px">
        <h3>Ben's Jungle: ${bj.length} Angebote</h3>
        <div class="scroll"><table>
          <tr><th>Angebot</th><th>Art / Sorte</th><th>Größe</th><th class="n">Preis inkl. MwSt.</th></tr>
          ${bj.map((o) => `<tr><td>${esc(o.name)}</td><td><em>${esc(o.plant)}</em></td><td>${o.size !== 'unknown' ? esc(o.size) : ''}</td><td class="n">${eur(o.price)}</td></tr>`).join('')}
        </table></div>
      </div>`;
  }
  legend();

  // ---------- cards ----------
  const kerriiStock = share(kerriiId, (o) => o.stock ?? 0);
  const leafId = subsOf(kerriiId)[0]?.id;
  const leafStock = sum(FA.filter((o) => o.group === leafId), (o) => o.stock ?? 0);
  const kerriiOffers = FA.filter((o) => topOf(o) === kerriiId).length;
  const leafOffers = FA.filter((o) => o.group === leafId).length;
  $('kerrii').innerHTML = `<span class="big">${pct(leafStock / kerriiStock)}</span>der Kerrii-Pflanzen im Bestand
    (${nf0.format(leafStock)} von ${nf0.format(kerriiStock)}, ${leafOffers} von ${kerriiOffers} Angeboten) sind bewurzelte
    Einzelblätter ohne Knoten. Sie bleiben lange grün, treiben aber fast nie aus; eine Pflanze wird daraus nicht (Perrone 2022).`;

  const carnosa = FA.filter((o) => topOf(o) === carnosaId);
  const others = FA.filter((o) => topOf(o) === 'other');
  const cheapest = carnosa.reduce((m, o) => (o.net < m.net ? o : m), carnosa[0]);
  $('carnosa').innerHTML = `<span class="big">${pct(carnosa.length / FA.length)}</span>der Angebote (${carnosa.length} von
    ${FA.length}) sind Carnosa-artig. Carnosa wird billig über Stecklinge vermehrt; die günstigste Sorte kostet ${eur(cheapest.net)}
    (<em>${esc(cheapest.plant)}</em>). Das drückt die Preise: Median ${eur(median(carnosa.map((o) => o.net)))} gegenüber
    ${eur(median(others.map((o) => o.net)))} bei den übrigen Arten.`;

  const rows = tops.flatMap((id) => [id, ...subsOf(id).map((s) => s.id)]).map((id) => {
    const g = groups[id];
    const f = median(FA.filter((o) => inGroup(o, id)).map((o) => o.net));
    const b = median(BJ.filter((o) => inGroup(o, id)).map((o) => o.price));
    return `<tr><td>${g.parent ? '&nbsp;└ ' + esc(g.name) : esc(g.name)}</td><td class="n">${eur(f)}</td><td class="n retail-only">${b != null ? eur(b) : '–'}</td></tr>`;
  });
  $('medians').innerHTML = `<tr><th></th><th class="n">FlorAccess<br>netto</th><th class="n retail-only">Ben's Jungle<br>inkl. MwSt.</th></tr>${rows.join('')}`;

  // ---------- wholesale vs retail ----------
  const byPlant = (xs) => xs.reduce((m, o) => ((m[o.plant_key] ??= []).push(o), m), {});
  const fa = byPlant(FA);
  const bj = byPlant(BJ);
  const pairs = Object.keys(fa).filter((k) => bj[k]).map((k) => {
    const f = fa[k].reduce((m, o) => (o.net < m.net ? o : m));
    const b = bj[k].reduce((m, o) => (o.price < m.price ? o : m));
    return { plant: f.plant, f, b, factor: b.net / f.net };
  }).sort((a, b) => b.factor - a.factor);
  const EXAMPLES = ['Hoya mirabilis', "Hoya 'Rosita'", "Hoya kerrii 'Splash'"];
  const ex = EXAMPLES.map((n) => pairs.find((p) => p.plant === n)).filter(Boolean);
  const bp = FA.filter((o) => /fitchii|soligamiana|wibergiae/i.test(o.plant) && /^9 cm/.test(o.pot ?? ''));
  const bpNames = [...new Set(bp.map((o) => o.plant))].map((n) => `<em>${esc(n)}</em>`);
  $('prices').innerHTML = `FlorAccess verkauft nur an Händler (Mindestbestellung 800 €), alle Preise netto. Für den Händlerkanal
    zählt dieser Vergleich: ${bpNames.join(' und ')} kosten bei FlorAccess ${eur(bp[0]?.net)} im 9-cm-Topf, also weniger als
    der Händlerpreis von 8 € im Businessplan (Kap. 6.4). Im Endkundengeschäft gelten andere Preise; dort verkaufen sich auch Arten,
    die FlorAccess günstiger hat: ${ex.map((p) => `<em>${esc(p.plant)}</em> ${eur(p.f.net)} bei FlorAccess, ${eur(p.b.price)} bei Ben's Jungle`).join('; ')}.`;
  $('compare-sum').textContent = `Alle ${pairs.length} Arten und Sorten, die beide Shops führen`;
  $('compare-table').innerHTML = `<tr><th>Art / Sorte</th><th class="n">FlorAccess netto</th><th>Topf / Höhe</th>
      <th class="n">Ben's Jungle inkl. MwSt.</th><th>Größe</th><th class="n">Faktor (netto)</th></tr>` +
    pairs.map((p) => `<tr class="${ex.includes(p) ? 'hl' : ''}"><td><em>${esc(p.plant)}</em></td><td class="n">${eur(p.f.net)}</td>
      <td>${esc(p.f.pot ?? '')} / ${esc(p.f.height ?? '')}</td><td class="n">${eur(p.b.price)}</td>
      <td>${p.b.size !== 'unknown' ? esc(p.b.size) : ''}</td><td class="n">${p.factor.toFixed(1).replace('.', ',')}×</td></tr>`).join('') +
    `<tr><td colspan="6" class="note">Je Shop das günstigste Angebot. Die Größen sind nicht immer gleich; Faktor = Ben's Jungle netto ÷ FlorAccess netto.</td></tr>`;

  // ---------- origin ----------
  const O = data.origin;
  const imp = O.filter((r) => r.import === 'wahrscheinlich').length;
  const wild = O.filter((r) => r.wild === 'nicht auszuschließen').length;
  const pick = (n) => O.find((r) => r.name === n);
  const exO = [["Hoya 'Lai Chau'", 'Fundort in Vietnam'], ['Hoya Sp Padang Sidempuan', 'Fundort auf Sumatra'],
    ["Hoya callistophylla 'KAL 16'", 'Sammelnummer']].filter(([n]) => pick(n));
  $('origin').innerHTML = `Bei <strong>${O.length} der ${FA.length} Angebote</strong> ist ein Import oder eine Wildentnahme denkbar.
    Das ist ein Indiz aus Name, Format und Preis, kein Befund: Bei ${imp} deuten Fundort, Sammelnummer oder asiatischer Handelsname
    auf einen Import hin, bei ${wild} ist eine Wildentnahme nicht auszuschließen. Beispiele:
    ${exO.map(([n, why]) => `<em>${esc(n)}</em> (${why})`).join(', ')}.`;
  $('origin-sum').textContent = `Alle ${O.length} Angebote mit möglichem Import oder Wildentnahme`;
  const KIND = (r) => (/^(Fundort|Sammelnummer)/.test(r.hint) ? 'Fundort- oder Sammelform' : /Reinart/.test(r.hint) ? 'Reinart ohne Herkunftsangabe' : 'Asiatischer Handelsname');
  const kinds = ['Alle', 'Fundort- oder Sammelform', 'Asiatischer Handelsname', 'Reinart ohne Herkunftsangabe'];
  let kind = 'Alle';
  let sortKey = null;
  let sortDir = 1;
  const COLS = [['name', 'Angebot'], ['import', 'Import'], ['wild', 'Wildentnahme'], ['hint', 'Indiz'], ['net', 'Preis netto', 'n'],
    ['pot', 'Topf / Höhe'], ['stock', 'Bestand', 'n'], ['line', 'Linie']];
  const tagCls = (v) => (v === 'wahrscheinlich' ? 'likely' : v === 'nicht auszuschließen' ? 'open' : '');
  function originTable() {
    let list = O.filter((r) => kind === 'Alle' || KIND(r) === kind);
    if (sortKey) list = [...list].sort((a, b) => ((a[sortKey] ?? '') > (b[sortKey] ?? '') ? 1 : (a[sortKey] ?? '') < (b[sortKey] ?? '') ? -1 : 0) * sortDir);
    $('origin-filters').innerHTML = kinds.map((k) => `<button class="${k === kind ? 'on' : ''}" data-k="${k}">${k} (${k === 'Alle' ? O.length : O.filter((r) => KIND(r) === k).length})</button>`).join('');
    for (const b of $('origin-filters').querySelectorAll('button')) b.onclick = () => { kind = b.dataset.k; originTable(); };
    $('origin-table').innerHTML = `<tr>${COLS.map(([k, l, c]) => `<th class="${c ?? ''}" data-k="${k}">${l}${sortKey === k ? (sortDir > 0 ? ' ▲' : ' ▼') : ''}</th>`).join('')}</tr>` +
      list.map((r) => `<tr><td>${esc(r.name)}</td><td><span class="tag ${tagCls(r.import)}">${esc(r.import)}</span></td>
        <td><span class="tag ${tagCls(r.wild)}">${esc(r.wild)}</span></td><td>${esc(r.hint)}</td><td class="n">${eur(r.net)}</td>
        <td>${esc(r.pot)} / ${esc(r.height)} cm</td><td class="n">${r.stock != null ? nf0.format(r.stock) : '–'}</td><td>${esc(r.line ?? '')}</td></tr>`).join('');
    for (const th of $('origin-table').querySelectorAll('th')) th.onclick = () => {
      sortDir = sortKey === th.dataset.k ? -sortDir : 1;
      sortKey = th.dataset.k;
      originTable();
    };
  }
  originTable();

  // ---------- method ----------
  $('method').textContent = `Gezählt sind alle Hoya-Angebote vom ${new Date(data.day).toLocaleDateString('de-DE')}, die eindeutig einer
    Art oder Sorte zugeordnet sind: ${FA.length} bei FlorAccess, ${BJ.length} bei Ben's Jungle. Nicht gezählt sind Mischungen wie
    „Hoya MIX“ und „Hoya kerrii MIX“ (22 Angebote bei FlorAccess). Sorten und Formen zählen zu ihrer Art. Preise in Euro, FlorAccess netto,
    Ben's Jungle inkl. 7 % MwSt.; Lagerwert = Bestand × Nettopreis. Gruppen und Einzelblatt-Zuordnung: GeniScent, nach Art und Foto.
    Herkunftseinschätzung: eigene Recherche vom 18.11.2026.`;

  // ---------- retail switch ----------
  const sw = $('retail');
  const apply = () => {
    document.body.classList.toggle('retail', sw.checked);
    if (sw.checked) $('compare').open = true;
    setTimeout(() => Object.values(charts).forEach((c) => { c.chart.resize(); c.draw(); }), 0);
  };
  sw.onchange = apply;
  apply();

  // ---------- hand-edited texts (texts/texts.json) and the edit version ----------
  const texts = await fetch('texts/texts.json', { cache: 'no-store' }).then((r) => (r.ok ? r.json() : {})).catch(() => ({}));
  const auto = {};
  for (const el of document.querySelectorAll('[data-edit]')) {
    const k = el.dataset.edit;
    auto[k] = el.innerHTML;
    if (texts[k] != null) el.innerHTML = texts[k];
    if (k === 'geniscent' && texts[k]) el.classList.remove('todo');
  }
  if (location.pathname.startsWith('/markus-edit')) editMode(texts, auto);

  function editMode(saved, automatic) {
    document.body.classList.add('editing');
    const pending = {};
    let focused = null;
    const bar = document.createElement('div');
    bar.className = 'editbar';
    bar.innerHTML = `<strong>Bearbeiten</strong><span id="eb-state">In einen Text klicken und ändern.</span>
      <button id="eb-reset" disabled>Text auf automatisch</button>
      <button id="eb-save" class="primary" disabled>Speichern</button>
      <a href="https://geniscent.duckdns.org:8446/" target="_blank" rel="noopener">Markus-Ansicht</a>`;
    document.body.prepend(bar);
    const state = $('eb-state');
    const update = () => {
      const n = Object.keys(pending).length;
      $('eb-save').disabled = !n;
      state.textContent = n ? `${n} ungespeicherte Änderung${n > 1 ? 'en' : ''}` : 'Alles gespeichert.';
    };
    for (const el of document.querySelectorAll('[data-edit]')) {
      const k = el.dataset.edit;
      el.contentEditable = 'true';
      el.spellcheck = true;
      el.classList.toggle('edited', saved[k] != null);
      el.addEventListener('focus', () => { focused = el; $('eb-reset').disabled = false; });
      el.addEventListener('input', () => { pending[k] = el.innerHTML; el.classList.add('edited'); update(); });
      el.addEventListener('click', (e) => e.target.closest('a') && e.preventDefault());
    }
    $('eb-reset').onclick = () => {
      if (!focused) return;
      const k = focused.dataset.edit;
      focused.innerHTML = automatic[k];
      focused.classList.remove('edited');
      if (k === 'geniscent') focused.classList.add('todo');
      pending[k] = null;
      update();
    };
    $('eb-save').onclick = async () => {
      $('eb-save').disabled = true;
      state.textContent = 'Speichere …';
      try {
        const r = await fetch('/api/markus/texts', { method: 'POST', credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ texts: pending }) });
        if (!r.ok) throw new Error(`Fehler ${r.status}`);
        const now = await r.json();
        for (const k of Object.keys(pending)) delete pending[k];
        for (const el of document.querySelectorAll('[data-edit]')) el.classList.toggle('edited', now[el.dataset.edit] != null);
        state.textContent = 'Gespeichert. Markus sieht jetzt diese Fassung.';
      } catch (e) {
        state.textContent = `Nicht gespeichert: ${e.message}`;
        $('eb-save').disabled = false;
      }
    };
    window.addEventListener('beforeunload', (e) => { if (Object.keys(pending).length) e.preventDefault(); });
  }
})();
