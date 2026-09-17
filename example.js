// Quick smoke test for the dev-swarm-training Node module.
import { searchKnowledge, listSkills, getSkill, stats } from './index.js';

console.log('=== stats() ===');
console.log(JSON.stringify(stats(), null, 2));

console.log('\n=== listSkills() ===');
console.log(listSkills());

console.log('\n=== searchKnowledge("LoRA rank alpha", { lane: "ml-training" }) ===');
for (const r of searchKnowledge('LoRA rank alpha', { lane: 'ml-training', limit: 2 })) {
  console.log(`- [${r.lane}] ${r.dataset}`);
  console.log(`  ${r.text.slice(0, 180).replace(/\n/g, ' ')}...`);
}

console.log('\n=== searchKnowledge("MCP handshake initialize") ===');
for (const r of searchKnowledge('MCP handshake initialize', { limit: 2 })) {
  console.log(`- [${r.lane}] ${r.dataset}`);
  console.log(`  ${r.text.slice(0, 180).replace(/\n/g, ' ')}...`);
}

console.log('\n=== getSkill("swarm-orchestration") (first 3 lines) ===');
console.log(getSkill('swarm-orchestration').split('\n').slice(0, 3).join('\n'));
