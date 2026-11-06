// Internal-only handoff. Never mounted as a Chrome/Executor operation.
// Cookie values stay inside the companion and the one-shot Python child's stdin.
export async function readXSession(dispatch) {
  const tabs = await dispatch('tabs.list', {url:'https://x.com/*'});
  const tab = tabs.find(t=>!t.discarded && new URL(t.url).origin==='https://x.com');
  if(!tab) throw Error('x_tab_required');
  const result = await dispatch('debugger.send',{tabId:tab.id,method:'Network.getCookies',params:{urls:['https://x.com/']}});
  const values = {};
  for(const c of result.cookies??[]) {
    if(!['x.com','.x.com'].includes(c.domain) || !['auth_token','ct0','twid'].includes(c.name) || !c.secure) continue;
    if(typeof c.value!=='string' || /[\x00-\x20\x7f;]/.test(c.value) || c.value.length>4096) throw Error('invalid_session');
    if(values[c.name] && values[c.name]!==c.value)throw Error('ambiguous_session');
    values[c.name]=c.value;
  }
  if(!values.auth_token || !values.ct0)throw Error('x_login_required');
  const userId=decodeURIComponent(values.twid??'').replaceAll('"','').match(/^u=(\d+)$/)?.[1];
  if(!userId)throw Error('x_identity_required');
  return {cookie:Object.entries(values).map(([k,v])=>`${k}=${v}`).join('; '),userId};
}
