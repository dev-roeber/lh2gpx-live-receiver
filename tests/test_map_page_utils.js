const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync('app/static/js/map-page-utils.js', 'utf8');
const fixedNow = Date.parse('2026-09-06T12:00:00Z');
const context = {
  Date: class extends Date {
    static now() { return fixedNow; }
  },
  window: {},
};
vm.runInNewContext(source, context, { filename: 'map-page-utils.js' });

const { getRelativeTime } = context.window.LH2GPXMapUtils;
assert.equal(getRelativeTime('2026-09-06T11:59:59.500Z'), 'jetzt');
assert.equal(getRelativeTime('2026-09-06T11:59:30Z'), 'vor 30s');
assert.equal(getRelativeTime('2026-09-06T11:45:00Z'), 'vor 15m');
assert.equal(getRelativeTime('2026-09-06T10:00:00Z'), 'vor 2h');
assert.equal(getRelativeTime('2026-09-05T12:00:00Z'), 'vor 1d');
assert.equal(Object.isFrozen(context.window.LH2GPXMapUtils), true);

console.log('map-page-utils tests passed');
