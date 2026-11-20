import {query, readInput, encodeInput} from './api.js';
import {el, evidence, table} from './table.js';

const byId = id => document.getElementById(id);
const settings = JSON.parse(byId('settings').textContent);
const links = [...document.querySelectorAll('[data-module]')];
const body = byId('grid-data');
const alert = byId('notice');
const live = byId('state');
const action = document.querySelector('#source button[type=submit]');
const topExport = byId('export');
let selected = Object.hasOwn(settings.tabs, location.hash.slice(1)) ? location.hash.slice(1) : 'domain';
let result = null;
let inputs = {};
let reviewVersion = 0;
let renderEpoch = 0;
let shiftDay = null;
const uploaded = new Map();

function notice(message, error = false) {
  alert.value = message;
  alert.classList.toggle('problem', error);
}

function tag(code) {
  return el('span', settings.reasons[code] || code, code === 'MATCH' ? 'state' : 'state problem');
}


function showEvidence(row) {
  const panel = byId('evidence-panel');
  const record = byId('evidence-key');
  const details = byId('signal');
  if (!row) {
    record.textContent = '';
    details.replaceChildren(el('p', '本批没有可采信记录', 'empty'));
    return;
  }
  record.textContent = row.key;
  const scale = new Map();
  for (const item of row.proof) {
    const magnitude = Math.abs(Number(item.value));
    if (Number.isFinite(magnitude)) scale.set(item.unit, Math.max(scale.get(item.unit) || 0, magnitude));
  }
  const content = el('dl', undefined, panel.dataset.instrument);
  for (const item of row.proof) {
    const measure = el('dt', item.metric);
    measure.append(el('output', item.unit ? `${item.value} ${item.unit}` : item.value));
    const value = el('dd');
    const magnitude = Math.abs(Number(item.value));
    const max = scale.get(item.unit);
    if (Number.isFinite(magnitude) && max) {
      const meter = el('span', undefined, 'track');
      meter.style.setProperty('--range', `${100 * magnitude / max}%`);
      meter.setAttribute('aria-hidden', 'true');
      value.append(meter);
    }
    content.append(measure, value);
  }
  details.replaceChildren(content);
}

function inspect(row) {
  const button = el('button', '查看依据', 'btn');
  button.type = 'button';
  button.addEventListener('click', () => showEvidence(row));
  const raw = evidence('原始字段', row.raw);
  const cell = el('div');
  cell.append(button, raw);
  return cell;
}

function setRun(report) {
  result = report;
  byId('created').textContent = `${report.manifest.created.slice(0, 19).replace('T', ' ')} UTC`;
  showEvidence(report.accepted[0]);
  const id = result.manifest.run_id;
  byId('run-id').textContent = id.slice(0, 9);
  byId('run-id').title = id;
  topExport.hidden = false;
  topExport.href = `/api/export/${id}`;
  const values = {...result.counts, delta: result.book.delta, mismatched: result.book.mismatched};
  for (const cell of document.querySelectorAll('[data-count]')) cell.textContent = values[cell.dataset.count];
  live.textContent = `批次 ${id.slice(0, 9)} · ${result.balanced ? '记录已对齐' : '记录数不符'}`;
}

const STRATEGY_LABELS = {freeze: '冻结备货分配', resequence: '重排未发车'};

function summarize(lines) {
  return lines.length ? lines.map(line => `${line.lot}:${line.quantity}`).join('，') : '—';
}

async function renderShifts(runId, ticket) {
  const overview = await query(`/api/shifts/${runId}`);
  if (!overview.shifts.length) {
    if (ticket === renderEpoch) body.replaceChildren(el('p', '本批没有可裁决班次', 'empty'));
    return;
  }
  if (!overview.shifts.some(item => item.shift === shiftDay)) shiftDay = overview.shifts[0].shift;
  const detail = await query(`/api/shifts/${runId}/${shiftDay}`);
  const root = el('div');
  const switcher = el('div', undefined, 'actions');
  for (const item of overview.shifts) {
    const tab = el('button', `${item.shift} · ${item.orders} 单${item.published ? ' · 已发布' : ''}`,
                   item.shift === shiftDay ? 'btn btn--primary' : 'btn');
    tab.type = 'button';
    tab.addEventListener('click', () => { shiftDay = item.shift; render(); });
    switcher.append(tab);
  }
  root.append(switcher);
  const mismatched = Number(detail.reconciliation.mismatched);
  root.append(el('p', mismatched ? `独立对账有 ${mismatched} 项差异，裁决可登记但不能发布`
                                 : '独立对账已对齐，确认后即可发布导出',
                 mismatched ? 'notice problem' : 'notice'));
  root.append(el('h3', '班次批次池'));
  const poolBox = el('div');
  table(poolBox, [['批次', 'lot'], ['到期', 'expiry'], ['品种', 'cultivar'],
                  ['库存', 'stock', 'num'], ['留样', 'retained', 'num'], ['可用', 'available', 'num'],
                  ['各自挑批', 'demanded', 'num'],
                  ['重复占用', row => row.over ? el('span', row.over, 'state problem') : '0', 'num'],
                  ['状态', row => row.blocked ? el('span', '到期停调', 'state problem') : '']],
        detail.pool);
  root.append(poolBox);
  const picked = new Set(detail.current ? detail.current.picked : []);
  const boxes = new Map();
  root.append(el('h3', '调出单与备货状态'));
  const orderBox = el('div');
  table(orderBox, [['业务键', 'key'], ['需求', 'demand', 'num'],
                   ['各自挑批', row => summarize(row.independent.lines)],
                   ['未满足', row => row.independent.unmet, 'num'],
                   ['已备货', row => {
                     const box = el('input');
                     box.type = 'checkbox';
                     box.checked = picked.has(row.key);
                     boxes.set(row.key, box);
                     return box;
                   }]], detail.orders);
  root.append(orderBox);
  const form = el('form', undefined, 'panel__body');
  const strategy = el('select');
  for (const [value, label] of Object.entries(STRATEGY_LABELS)) {
    const option = el('option', label);
    option.value = value;
    if (detail.current && detail.current.strategy === value) option.selected = true;
    strategy.append(option);
  }
  const submit = el('button', '裁决班次', 'btn btn--primary');
  submit.type = 'submit';
  const action = el('div', undefined, 'actions');
  action.append(el('span', '裁决策略'), strategy, submit);
  form.append(action);
  form.addEventListener('submit', async event => {
    event.preventDefault();
    submit.disabled = true;
    try {
      const chosen = [...boxes.entries()].filter(([, box]) => box.checked).map(([key]) => key);
      const payload = await query(`/api/shifts/${runId}/${shiftDay}/adjudicate`,
                                  {strategy: strategy.value, picked: chosen,
                                   base_version: detail.current ? detail.current.version : 0});
      notice(`裁决已登记 · 版本 ${payload.version}`);
      await render();
    } catch (error) { notice(error.message, true); }
    finally { submit.disabled = false; }
  });
  root.append(form);
  if (detail.current) {
    const current = detail.current;
    root.append(el('h3', `当前裁决 · 版本 ${current.version} · ${STRATEGY_LABELS[current.strategy]}`));
    const totals = current.result.totals;
    root.append(el('p', `需求 ${totals.demand} · 分配 ${totals.allocated} · 未满足 ${totals.unmet}`, 'notice'));
    const resultBox = el('div');
    table(resultBox, [['业务键', 'key'], ['状态', 'state'], ['需求', 'demand', 'num'],
                      ['班次分配', row => summarize(row.lines)],
                      ['未满足', row => Number(row.unmet) ? el('span', row.unmet, 'state problem') : '0', 'num'],
                      ['挑批变更', row => row.changed ? el('span', '已重排', 'state') : '']],
          current.result.orders);
    root.append(resultBox);
    const usageBox = el('div');
    table(usageBox, [['批次', 'lot'], ['可用', 'available', 'num'], ['已分配', 'allocated', 'num'],
                     ['剩余', 'left', 'num'], ['留样', 'retained', 'num']],
          current.result.pool);
    root.append(usageBox);
    root.append(el('h3', '班次复核'));
    const timelineBox = el('div');
    table(timelineBox, [['版本', 'version', 'num'], ['裁决版本', 'adjudication', 'num'],
                        ['结论', 'decision'], ['复核意见', 'note'], ['登记 UTC', 'changed']],
          detail.reviews);
    root.append(timelineBox);
    const reviewForm = el('form', undefined, 'panel__body');
    const note = el('textarea');
    note.maxLength = 500;
    note.setAttribute('aria-label', '复核意见');
    const decision = el('select');
    for (const label of ['确认', '退回']) {
      const option = el('option', label);
      decision.append(option);
    }
    const commit = el('button', '提交班次复核', 'btn btn--primary');
    commit.type = 'submit';
    const download = el('button', '导出班次证据', 'btn');
    download.type = 'button';
    const reviewAction = el('div', undefined, 'actions');
    reviewAction.append(decision, commit, download);
    reviewForm.append(note, reviewAction);
    reviewForm.addEventListener('submit', async event => {
      event.preventDefault();
      commit.disabled = true;
      try {
        await query(`/api/shifts/${runId}/${shiftDay}/review`,
                    {version: current.version, decision: decision.value, note: note.value});
        notice('班次复核已登记');
        await render();
      } catch (error) { notice(error.message, true); }
      finally { commit.disabled = false; }
    });
    download.addEventListener('click', async () => {
      download.disabled = true;
      try {
        const response = await fetch(`/api/shifts/${runId}/${shiftDay}/export`);
        if (!response.ok) throw Error((await response.json()).detail || '导出被拒');
        const link = el('a');
        link.href = URL.createObjectURL(await response.blob());
        link.download = `shift-${shiftDay}.json`;
        link.click();
        URL.revokeObjectURL(link.href);
      } catch (error) { notice(error.message, true); }
      finally { download.disabled = false; }
    });
    root.append(reviewForm);
  }
  if (ticket === renderEpoch) body.replaceChildren(root);
}

async function render() {
  const ticket = ++renderEpoch;
  const stage = selected;
  byId('phase').textContent = settings.tabs[stage];
  byId('review').hidden = true;
  for (const link of links) {
    if (link.dataset.module === stage) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  }
  if (!result) return;
  const id = result.manifest.run_id;
  const raw = row => evidence('来源字段', row.raw);
  const key = ['业务键', 'key'];
  const line = ['行号', 'line', 'num'];
  try {
    let view, rows;
    if (stage === 'domain') {
      view = [key, [`复算值 · ${settings.unit}`, 'amount', 'num'], line, ['明细依据', inspect]];
      rows = result.accepted;
    } else if (stage === 'quality') {
      view = [key, line, ['判定', row => tag(row.code)], ['说明', 'detail'], ['字段', raw]];
      rows = [...result.quarantine, ...result.suppressed].sort((a,b) => a.line-b.line);
    } else if (stage === 'reconcile') {
      view = [key, ['实际', 'amount', 'num'], ['外部账', 'reference', 'num'], ['差值', 'delta', 'num'], ['外部行', 'book_line', 'num'], ['结论', row => tag(row.code)]];
      rows = [...result.book.rows].sort((a,b) => Number(a.code === 'MATCH') - Number(b.code === 'MATCH'));
    } else if (stage === 'intake') {
      const intake = await query('/api/intake', inputs);
      view = [line, ['分类', 'kind'], ['字段', raw]];
      rows = [...intake.rows.map(row => ({...row,kind:'完整记录'})), ...intake.rejected.map(row => ({...row,kind:'坏行'})),
              ...intake.blank_lines.map(line => ({line,kind:'空白行',raw:[]})),
              ...intake.header_lines.map(line => ({line,kind:'重复表头',raw:[]}))].sort((a,b) => a.line-b.line);
    } else if (stage === 'contract') {
      const contract = await query('/api/contract', inputs);
      view = [key, line, ['修订', 'revision', 'num'], ['来源时刻 UTC', 'time'], ['字段', row => evidence('归一值', Object.entries(row.fields).map(([k,v]) => `${k} · ${v}`))]];
      rows = contract.accepted;
    } else if (stage === 'shifts') {
      await renderShifts(id, ticket);
      return;
    } else if (stage === 'runs') {
      const runs = await query('/api/runs');
      view = [['指纹','id'], ['创建 UTC','created'], ['操作', row => {
        const current = row.id === id;
        const button = el('button',current ? '复算当前批' : '打开此批','btn');
        button.addEventListener('click', async () => {
          button.disabled = true;
          try {
            if (current) {
              setRun(await query(`/api/runs/${id}/replay`, {}));
              notice('复算已核对');
            } else {
              const [past, original] = await Promise.all([
                query(`/api/runs/${row.id}`), query(`/api/runs/${row.id}/source`),
              ]);
              inputs = original;
              setRun(past);
              notice('已打开历史批次');
              await render();
            }
          }
          catch (error) { notice(error.message, true); }
          finally { button.disabled = false; }
        });
        return button;
      }]];
      rows = runs;
    } else {
      const timeline = await query(`/api/review/${id}`);
      view = [['版本','version','num'], ['结论','decision'], ['复核意见','note'], ['登记 UTC','changed']];
      rows = timeline;
      if (ticket === renderEpoch) {
        reviewVersion = timeline[0]?.version || 0;
        byId('review').hidden = false;
      }
    }
    if (ticket === renderEpoch) table(body, view, rows);
  } catch (error) {
    if (ticket === renderEpoch) notice(error.message, true);
  }
}

window.addEventListener('hashchange', () => {
  selected = Object.hasOwn(settings.tabs, location.hash.slice(1)) ? location.hash.slice(1) : 'domain';
  render();
});
byId('sample').addEventListener('click', async () => {
  const paths = ['shift', 'external'];
  try {
    const responses = await Promise.all(paths.map(name => fetch(`/api/samples/${name}`)));
    if (responses.some(item => !item.ok)) throw Error('样例暂时不可用');
    const files = await Promise.all(responses.map(item => item.arrayBuffer()));
    for (const [index,name] of ['source','book'].entries()) {
      const decoded = new TextDecoder('utf-8').decode(files[index]);
      byId(`${name}-csv`).value = decoded;
      uploaded.set(name,{text:byId(`${name}-csv`).value,bytes:files[index]});
    }
    byId('source-file').value = '';
    byId('book-file').value = '';
    document.querySelector('#source details').open = true;
    notice('样例已载入');
  } catch (error) { notice(error.message, true); }
});
for (const name of ['source','book']) {
  byId(`${name}-file`).addEventListener('change', async event => {
    const file = event.target.files[0];
    if (!file) return;
    action.disabled = true;
    try {
      const [text,bytes] = await readInput(file);
      byId(`${name}-csv`).value = text;
      uploaded.set(name,{text:byId(`${name}-csv`).value,bytes});
      notice(`已读取 ${file.name}`);
    } catch (error) {
      event.target.value = '';
      notice(error.message, true);
    } finally { action.disabled = false; }
  });
}
byId('source').addEventListener('submit', async event => {
  event.preventDefault();
  const candidate = {};
  for (const [control,name] of [['source','data'],['book','book']]) {
    const text = byId(`${control}-csv`).value;
    const original = uploaded.get(control);
    if (original && text === original.text) candidate[`${name}_base64`] = encodeInput(original.bytes);
    else if (text.length || original) candidate[name] = text;
  }
  action.disabled = true;
  ++renderEpoch;
  notice('计算中');
  try {
    const report = await query('/api/runs', candidate);
    inputs = candidate;
    setRun(report);
    notice('批次已计算');
    await render();
  } catch (error) { notice(error.message, true); }
  finally { action.disabled = false; }
});
byId('review').addEventListener('submit', async event => {
  event.preventDefault();
  const id = result.manifest.run_id;
  const note = byId('review-note');
  try {
    await query(`/api/review/${id}`, {version: reviewVersion, decision: byId('decision').value, note: note.value});
    notice('复核已登记');
    note.value = '';
    await render();
  } catch (error) { notice(error.message, true); }
});
render();
