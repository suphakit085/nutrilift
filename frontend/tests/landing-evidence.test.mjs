import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { test } from 'node:test';
const read=path=>readFileSync(new URL(path,import.meta.url),'utf8');
const evidence=JSON.parse(read('../src/lib/landing-evidence.json'));

test('published score means use their paired numerators, denominator and current scale',()=>{
  assert.equal(evidence.answerCount,evidence.questionCount*2);
  assert.equal(evidence.scoreScale.max,2);
  assert.equal(evidence.scoreScale.min,0);
  for(const row of evidence.metrics){
    assert.ok(row.pairs>0&&row.pairs<=evidence.questionCount);
    for(const mode of ['withRag','withoutRag']){
      assert.ok(row[mode+'Total']>=0&&row[mode+'Total']<=2*row.pairs);
      assert.equal(row[mode],(row[mode+'Total']/row.pairs).toFixed(2));
    }
  }
  assert.equal(evidence.metrics[0].pairs,evidence.questionCount);
  assert.equal(evidence.metrics[1].pairs,evidence.questionCount);
  assert.ok(evidence.metrics[2].pairs<evidence.questionCount);
  assert.equal(evidence.retrieval.hitAt6,Number((100*evidence.retrieval.hits/evidence.retrieval.eligible).toFixed(2)));
  assert.ok(evidence.retrieval.mrr<=evidence.retrieval.hitAt6/100);
});

test('published corpus counts and protein example retain the current source units',()=>{
  const cards=readdirSync(new URL('../../knowledge/cards/',import.meta.url)).filter(n=>n.endsWith('.md')&&!n.startsWith('_'));
  assert.equal(evidence.knowledgeCardCount,cards.length);
  // Scores on the page were measured on an older, smaller corpus; the page must say so.
  assert.equal(evidence.evaluatedKnowledgeCardCount,26);
  assert.ok(evidence.evaluatedKnowledgeCardCount<=evidence.knowledgeCardCount);
  const card=read('../../knowledge/cards/protein-requirement.md');
  const front=card.split('---')[1];
  assert.equal((front.match(/^- /gm)||[]).length,5);
  const page=read('../src/app/page.tsx');
  assert.ok(page.includes('1.4–2.0'));
  assert.ok(card.includes('1.4-2.0'));
  assert.ok(page.includes('https://doi.org/10.1186/s12970-017-0177-8'));
  assert.ok(page.includes('คนสุขภาพดี'));
  assert.ok(!page.includes('row.p}'));
  assert.ok(!page.includes('อ้างแหล่งที่ไม่มีจริง'));
  assert.ok(page.includes('85 คู่ที่มีคะแนนครบ'));
  assert.ok(page.includes('เฉลยค้นคืนส่วนนี้ทบทวนด้วย AI'));
  assert.equal(page.split('evidence.evaluatedKnowledgeCardCount').length-1,3);
  assert.ok(page.includes('ยังไม่ได้วัดใหม่'));
});
