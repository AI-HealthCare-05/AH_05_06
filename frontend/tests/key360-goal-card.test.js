const { test } = require('node:test');
const assert = require('node:assert/strict');
const { read } = require('./source');

test('KEY-360: 목표 카드 전용 렌더러·CSS와 화면 선택 문구를 제거한다', () => {
  const patient = read('patient_wireframe/js/guide.js');
  const preview = read('js/patient-guide-cards.js');
  const css = read('patient_wireframe/css/guide.css');
  assert.doesNotMatch(patient, /goalCard|goal-chart|나의 목표|medication\.goals/);
  assert.doesNotMatch(preview, /function (?:patientGoalItemHtml|patientGoalCardHtml|goalChartPct)\b/);
  assert.doesNotMatch(css, /\.goal-(?:item|head|date|name|range-label|chart|no-chart|say)\b/);
  assert.match(patient, /activeAxis\.goal/, '생활관리 목표는 유지한다');
});
