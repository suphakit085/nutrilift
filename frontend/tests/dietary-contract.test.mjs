import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {test} from "node:test";

test("profile and chat choices match the backend dietary catalog, including legacy nuts", () => {
  const client=JSON.parse(readFileSync(new URL("../src/lib/dietary-options.json",import.meta.url),"utf8"));
  const server=JSON.parse(readFileSync(new URL("../../backend/app/services/dietary-options.json",import.meta.url),"utf8"));
  assert.deepEqual(client,server);
  const values=client.flatMap(group=>group.options.map(item=>item.value));
  assert.equal(new Set(values).size,values.length);
  for(const value of ["แพ้ถั่ว","แพ้ถั่วลิสง","แพ้ถั่วเปลือกแข็ง","แพ้ถั่วเหลือง","แพ้งา"])assert.ok(values.includes(value));
});
