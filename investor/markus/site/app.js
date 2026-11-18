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

  // Ben's Jungle (retail switch): its figure sits under FlorAccess's in the same size, dark green, with a small note below.
  const tile = (l, v, r = '') => `<div class="tile"><div class="l">${l}</div><div class="v">${v}</div>${r}</div>`;
  const bjr = (v, note = "Ben's Jungle") => `<div class="retail-only bj"><div class="v">${v}</div><div class="r">${note}</div></div>`;
  $('tiles').innerHTML =
    tile('Medianpreis', eur(median(FA.map((o) => o.net))) + '<small style="font-size:12px;font-weight:400"> netto</small>',
      bjr(eur(median(BJ.map((o) => o.price))), "Ben's Jungle, inkl. MwSt.")) +
    tile('Arten', species(FA), bjr(species(BJ))) +
    tile('Angebote', FA.length, bjr(BJ.length)) +
    tile('Pflanzen im Bestand', nf0.format(stockAll), bjr('–', "Ben's Jungle: nicht veröffentlicht")) +
    tile('Warenwert zu Verkaufspreisen', eur0(valueAll), bjr('–', "Ben's Jungle: nicht veröffentlicht"));

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
        // Transparent filler over the rest of the group's slice: acts like the group itself on hover/click.
        if (rest > 0) inner.push({ name: '', value: rest, gid: p.id, rest: outer.indexOf(p), itemStyle: { color: 'transparent' },
          tooltip: { show: false }, emphasis: { disabled: true } });
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
              formatter: (p) => (p.percent >= 6 ? `${Math.round(p.percent)} %` : ''), fontSize: 12, fontWeight: 600 },
            itemStyle: { borderColor: '#fff', borderWidth: 2, borderRadius: 4 }, emphasis: { scale: false },
            data: outer.map((p) => ({ name: groups[p.id].name, value: p.v, gid: p.id, label: { color: textOn(groups[p.id].color) },
              itemStyle: { color: groups[p.id].color, opacity: !selected || selected === p.id || groups[selected]?.parent === p.id ? 1 : 0.35 } })) },
          { type: 'pie', radius: [`${r0}%`, `${r0 + 0.6 * (r1 - r0)}%`], center: ['50%', '50%'], label: { show: false },
            labelLine: { show: false }, emphasis: { scale: false }, z: 3, data: inner },
        ],
      }, true);
    };
    new ResizeObserver(() => { chart.resize(); draw(); }).observe(el);
    draw();
    return { chart, draw };
  }

  // Variety as it looks from the offer list: one slice per species (its cultivars and forms merged into it),
  // sized by the number of offers, independent of stock. Coloured by group so the link to the next charts shows.
  function speciesName(key, offers) {
    const own = offers.find((o) => o.plant_key === key);
    if (own) return own.plant;
    const p = offers[0].plant;
    return key.startsWith('s') ? p.split(' ').slice(0, 2).join(' ') : p;
  }
  function varietyChart(el, offers) {
    const chart = echarts.init(el, null, { renderer: 'svg' });
    const draw = () => {
      const bySpecies = {};
      for (const o of offers) (bySpecies[o.species_key] ??= []).push(o);
      const slices = Object.entries(bySpecies).map(([key, os]) => {
        const count = {};
        for (const o of os) count[topOf(o)] = (count[topOf(o)] ?? 0) + 1;
        const grp = Object.entries(count).sort((a, b) => b[1] - a[1])[0][0];
        const variants = [...new Set(os.map((o) => o.plant))];
        return { key, name: speciesName(key, os), value: os.length, grp: grp === 'other' ? 'other' : Number(grp), variants };
      });
      // Only the namesake species (carnosa, kerrii, wayettii) carry the group colour; everything else is grey.
      const NAMESAKE = /carnosa|kerrii|wayet/i;
      for (const sl of slices) sl.colorGrp = sl.grp !== 'other' && NAMESAKE.test(sl.name) ? sl.grp : 'other';
      const order = (g) => tops.indexOf(g);
      slices.sort((a, b) => order(a.colorGrp) - order(b.colorGrp) || b.value - a.value || a.name.localeCompare(b.name));
      const seen = {};
      const data = slices.map((sl) => {
        const i = (seen[sl.colorGrp] = (seen[sl.colorGrp] ?? -1) + 1);
        const base = groups[sl.colorGrp].color;
        const color = i % 3 === 0 ? base : i % 3 === 1 ? shade(base, 0.18) : tint(base, 0.25);
        const dim = selected && selected !== sl.grp && groups[selected]?.parent !== sl.grp;
        return { name: sl.name, value: sl.value, gid: sl.grp, nocard: sl.colorGrp === 'other', variants: sl.variants, itemStyle: { color, opacity: dim ? 0.35 : 1 } };
      });
      chart.setOption({
        animation: false,
        tooltip: {
          trigger: 'item', backgroundColor: '#fff', borderColor: css('--line'), textStyle: { color: css('--ink'), fontSize: 13 },
          formatter: (p) => {
            const v = p.data.variants;
            const list = v.length > 1 ? `<br><span style="color:${css('--muted')}">${v.slice(0, 8).map(esc).join('<br>')}${v.length > 8 ? '<br>…' : ''}</span>` : '';
            return `${p.marker}<b>${esc(p.name)}</b><br>${p.value} Angebot${p.value > 1 ? 'e' : ''} · ${p.percent} % · ${esc(groups[p.data.gid].name)}${list}`;
          },
        },
        series: [{ type: 'pie', radius: ['44%', '76%'], center: ['50%', '50%'], label: { show: false }, labelLine: { show: false },
          itemStyle: { borderColor: '#fff', borderWidth: 1.5, borderRadius: 2 }, emphasis: { scale: false }, data }],
      }, true);
    };
    new ResizeObserver(() => { chart.resize(); draw(); }).observe(el);
    draw();
    return { chart, draw };
  }
  // Dark label text on light slices (Kerrii yellow), white elsewhere.
  function textOn(hex) {
    const n = parseInt(hex.replace('#', ''), 16);
    const [r, g, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255];
    return 0.299 * r + 0.587 * g + 0.114 * b > 165 ? '#3a2f08' : '#fff';
  }
  // Hovering a Kerrii or Carnosa slice highlights its text card.
  function linkCards(chart) {
    const cardFor = (gid) => {
      const top = groups[gid]?.parent ?? gid;
      const name = groups[top]?.name ?? '';
      return document.querySelector(`.card[data-group="${/^Kerrii/.test(name) ? 'kerrii' : /^Carnosa/.test(name) ? 'carnosa' : ''}"]`);
    };
    let off = null;
    chart.on('mouseover', (p) => {
      cancelAnimationFrame(off);
      document.querySelectorAll('.card.hl').forEach((c) => c.classList.remove('hl'));
      if (p.data?.gid != null && !p.data.nocard) cardFor(p.data.gid)?.classList.add('hl');
      if (p.data?.rest != null) {
        chart.dispatchAction({ type: 'highlight', seriesIndex: 0, dataIndex: p.data.rest });
        chart.dispatchAction({ type: 'showTip', seriesIndex: 0, dataIndex: p.data.rest });
      }
    });
    chart.on('mouseout', (p) => {
      if (p.data?.rest != null) {
        chart.dispatchAction({ type: 'downplay', seriesIndex: 0, dataIndex: p.data.rest });
        chart.dispatchAction({ type: 'hideTip' });
      }
      off = requestAnimationFrame(() => document.querySelectorAll('.card.hl').forEach((c) => c.classList.remove('hl')));
    });
  }
  function tint(hex, amount) {
    const n = parseInt(hex.replace('#', ''), 16);
    const c = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((v) => Math.round(v + (255 - v) * amount));
    return `#${c.map((v) => v.toString(16).padStart(2, '0')).join('')}`;
  }

  charts.variety = varietyChart($('c-variety'), FA);
  charts.stock = donut($('c-stock'), FA, (o) => o.stock ?? 0, 'Pflanzen');
  charts.value = donut($('c-value'), FA, value, '€');
  charts.retail = donut($('c-retail'), BJ, () => 1, 'Angebote');
  Object.values(charts).forEach((c) => linkCards(c.chart));

  const kerriiId = tops.find((id) => groups[id].name === 'Kerrii-artig');
  const carnosaId = tops.find((id) => groups[id].name === 'Carnosa-artig');
  const share = (id, f) => sum(FA.filter((o) => topOf(o) === id), f);
  $('caption').textContent = `Kerrii-artige sind ${pct(share(kerriiId, (o) => o.stock ?? 0) / stockAll)} der Pflanzen, aber nur ${pct(share(kerriiId, value) / valueAll)} des Lagerwerts – überwiegend günstige Einzelblätter.`;

  // ---------- legend ----------
  function legend() {
    const items = tops.flatMap((id) => [id, ...subsOf(id).map((s) => s.id)]);
    $('legend').innerHTML = items.map((id) => {
      const g = groups[id];
      return `<span class="chip"><span class="sw${g.parent ? ' hollow' : ''}" style="${g.parent ? `border-color:${g.color}` : `background:${g.color}`}"></span>${esc(g.parent ? '└ ' + g.name : g.name)}</span>`;
    }).join('');
  }
  legend();

  // ---------- cards ----------
  const kerriiStock = share(kerriiId, (o) => o.stock ?? 0);
  const leafId = subsOf(kerriiId)[0]?.id;
  const leafStock = sum(FA.filter((o) => o.group === leafId), (o) => o.stock ?? 0);
  const kerriiOffers = FA.filter((o) => topOf(o) === kerriiId).length;
  const leafOffers = FA.filter((o) => o.group === leafId).length;
  const leafShareAll = leafStock / stockAll;
  const third = Math.abs(leafShareAll - 1 / 3) < 0.03 ? 'ein Drittel' : pct(leafShareAll);
  $('kerrii').innerHTML = `<span class="big">${pct(leafStock / kerriiStock)}</span>der Kerrii-Pflanzen sind Einzelblätter ohne Knoten,
    das ist ${third} des gesamten Hoya-Bestands. <strong>Aus einem Einzelblatt wird fast nie eine Pflanze.</strong>`;

  const carnosa = FA.filter((o) => topOf(o) === carnosaId);
  const others = FA.filter((o) => topOf(o) === 'other');
  const cheapest = carnosa.reduce((m, o) => (o.net < m.net ? o : m), carnosa[0]);
  $('carnosa').innerHTML = `<span class="big">${pct(carnosa.length / FA.length)}</span>der Angebote sind Carnosa-artig
    (${carnosa.length} von ${FA.length}). Die Auswahl ist kleiner, als die Zahl der Angebote vermuten lässt.`;

  // Our planned species = the species in GeniScent's stock ("Hoya Bestand November 2026", one entry per
  // species; unclear "Mystery" and "Elephant" plants left out). Counted when FlorAccess has no offer of
  // that species (any form or cultivar) at 8 € net or less on the snapshot day.
  const OUR_SPECIES = ['australis', ['bella', 'lanceolata'], 'burtoniae', 'callistophylla', 'calycina', 'carnosa', 'caudata',
    'clemensiorum', 'cumingiana', 'curtisii', 'davidcummingii', 'erythrina', 'fitchii', 'fungii', 'fuscomarginata', 'heuschkeliana',
    'icensis', 'imperialis', 'kentiana', 'kerrii', 'kloppenburgii', 'krohniana', 'linearis', 'macgregorii', 'mathilde', 'mirabilis',
    'nummularioides', 'obovata', ['parasitica'], 'paxtonii', 'pubicalyx', 'retusa', 'serpens', 'shepherdii', 'sigillatis', 'undulata',
    ['wayetii', 'wayettii'], 'wightii'];
  const hasCheap = (keys) => FA.some((o) => o.net <= 8 && [].concat(keys).some((k) =>
    new RegExp(`\\b${k}\\b`, 'i').test(`${o.plant} ${o.name}`)));
  const gapCount = OUR_SPECIES.filter((k) => !hasCheap(k)).length;

  $('lead').innerHTML = `FlorAccess hat viele Hoyas, aber nicht das, was unsere Händler ab 2027 suchen. Es gibt dort eine
    Mindestbestellung von 800 €, im Kern Carnosa und Kerrii, und ${third} des Bestands sind Einzelblätter.<br><br>
    Die selteneren Arten kosten dort im Median ${eur(median(others.map((o) => o.net)))} netto, unsere Herstellungskosten liegen bei
    3,20 € (2,50 € bei voller Auslastung). ${gapCount} von ${OUR_SPECIES.length} unserer geplanten Arten führt FlorAccess nicht oder nur über 8 €.<br><br>
    Die Analysesoftware, die mit diesem Bericht in Betrieb gegangen ist, nutzen wir ab jetzt für die Sortimentsplanung.`;

  const medRows = tops.flatMap((id) => [id, ...subsOf(id).map((s) => s.id)])
    .map((id) => ({ id, g: groups[id], v: median(FA.filter((o) => inGroup(o, id)).map((o) => o.net)) }))
    .filter((r) => r.v != null).sort((a, b) => b.v - a.v);
  const medChart = echarts.init($('medians'), null, { renderer: 'svg' });
  medChart.setOption({
    animation: false, textStyle: { fontFamily: 'system-ui, sans-serif' },
    grid: { left: 4, right: 52, top: 4, bottom: 4, containLabel: true },
    xAxis: { type: 'value', show: false },
    yAxis: { type: 'category', inverse: false, data: medRows.map((r) => (r.g.parent ? r.g.name : r.g.name)),
      axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: css('--ink-2'), fontSize: 12 } },
    series: [{ type: 'bar', barWidth: '62%', data: medRows.map((r) => ({ value: r.v, itemStyle: { color: r.g.color, borderRadius: [0, 3, 3, 0] } })),
      label: { show: true, position: 'right', formatter: (p) => eur(p.value), color: css('--ink'), fontSize: 12 } }],
    tooltip: { show: false },
  });
  new ResizeObserver(() => medChart.resize()).observe($('medians'));

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
  const bp = FA.filter((o) => /fitchii|soligamiana/i.test(o.plant) && /^9 cm/.test(o.pot ?? ''));
  const bpNames = [...new Set(bp.map((o) => o.plant))].map((n) => `<em>${esc(n)}</em>`);
  $('prices').innerHTML = `Im Verkauf an Händler zählt der Großhandelspreis. ${bpNames.join(' und ')} gibt es bei FlorAccess für
    ${eur(bp[0]?.net)} im 9-cm-Topf, das liegt unter unserem Händlerpreis von 8 €.`;

  // ---------- origin ----------
  const O = data.origin;
  const imp = O.filter((r) => r.import === 'wahrscheinlich').length;
  const wild = O.filter((r) => r.wild === 'nicht auszuschließen').length;
  const pick = (n) => O.find((r) => r.name === n);
  const exO = [["Hoya 'Lai Chau'", 'Fundort in Vietnam'], ['Hoya Sp Padang Sidempuan', 'Fundort auf Sumatra'],
    ["Hoya callistophylla 'KAL 16'", 'Sammelnummer']].filter(([n]) => pick(n));
  $('origin').innerHTML = `Bei <strong>${O.length} von ${FA.length} Angeboten</strong> deuten Name, Format oder Preis auf einen Import
    oder eine Wildentnahme hin. Das ist ein Indiz, kein Befund.`;
  $('origin-sum').textContent = `Alle ${O.length} Angebote`;
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
  $('method').textContent = `Stand ${new Date(data.day).toLocaleDateString('de-DE')}. Gezählt sind Angebote, die sich eindeutig einer
    Art oder Sorte zuordnen lassen (FlorAccess ${FA.length}, Ben's Jungle ${BJ.length}), ohne Mischungen. Die Gruppen und die Einzelblätter
    haben wir selbst nach Art und Foto zugeordnet. Der Preisverlauf stammt aus archivierten FlorAccess-Seiten im Internet Archive.`;

  // ---------- retail switch ----------
  const sw = $('retail');
  const apply = () => {
    document.body.classList.toggle('retail', sw.checked);
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
