'use strict';
// Exercise actual controller functions against state transitions, without a browser or provider.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../src/thesisledger/static/app.js'), 'utf8');
function functions(start, end) {
  const first = source.indexOf('  ' + start), last = source.indexOf('  ' + end, first);
  assert(first >= 0 && last > first, 'Controller function boundaries must exist');
  return source.slice(first, last);
}
function fixture() {
  const state = hash => ({companies:[{symbol:'EXE',history:[{input_hash:hash}]}]});
  const ui = {page:'lab',symbol:'EXE',state:state('old'),details:new Map(),connected:true,
    lab:{symbol:'EXE',data:{baseline:{base:24.83}},parameters:[{key:'realized_price',value:3.5}],values:{realized_price:4},revision:1,
      run:{run_id:'saved-old'},verification:{verified:true},timer:null}};
  const context = {ui, nextState:state('old'), labRequests:0, clearTimeout,
    array:value => Array.isArray(value) ? value : [], companies:() => ui.state.companies,
    preferredLabSymbol:() => 'EXE', labParameters:() => ui.lab.parameters,
    connection:() => {}, render:() => {}, toast:() => {}, loadCompany:async () => {}, loadReports:async () => {}};
  context.request = async url => {
    if (url === '/api/state') return context.nextState;
    if (url === '/api/runs') return {runs:[],skipped:0};
    assert.equal(url, '/api/company/EXE/lab');context.labRequests++;
    return {baseline:{base:46.65},parameters:[{key:'realized_price',value:4}]};
  };
  vm.createContext(context);
  vm.runInContext(functions('function setState(', 'async function mutate(') + '\n' +
    functions('async function loadLab(', 'function updateLabOutputs(') + '\nthis.api={setState,refresh,loadLab};', context);
  return {context, ui, state};
}
(async () => {
  let test = fixture();
  const run = test.ui.lab.run, verification = test.ui.lab.verification;
  await test.context.api.refresh();
  assert.equal(test.ui.lab.values.realized_price,4);
  assert.equal(test.ui.lab.run,run);assert.equal(test.ui.lab.verification,verification);
  assert.equal(test.context.labRequests,0);

  test=fixture();test.ui.page='monitor';test.context.nextState=test.state('new');
  await test.context.api.refresh();
  assert.equal(test.ui.lab.data,null);assert.equal(test.ui.lab.run,null);
  await test.context.api.loadLab('EXE');
  assert.equal(test.context.labRequests,1);assert.equal(test.ui.lab.data.baseline.base,46.65);
  assert.equal(test.ui.lab.values.realized_price,4);

  test=fixture();test.ui.page='research';
  test.context.api.setState(test.state('accepted'));
  assert.equal(test.ui.lab.data,null);assert.equal(test.ui.lab.verification,null);
  await test.context.api.loadLab('EXE');
  assert.equal(test.context.labRequests,1);assert.equal(test.ui.lab.data.baseline.base,46.65);
  console.log('UI state regressions: 3 passed (unchanged refresh, off-page refresh, accepted baseline).');
})().catch(error => {console.error(error);process.exitCode=1;});
