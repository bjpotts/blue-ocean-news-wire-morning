import { supabase } from './auth.js';

// Data layer for the Market Wrap Up app's dynamic content.
// Tables (see supabase/migrations/0001_market_wrap_up_schema.sql):
//   digest_runs, market_data, performers, capital_raises, news, weather,
//   saved_items (user-owned, RLS via auth.uid()).

// --- Digest runs -----------------------------------------------------------

export async function listRuns(limit = 50) {
  const { data, error } = await supabase
    .from('digest_runs')
    .select('*')
    .order('edition_date', { ascending: false })
    .limit(limit);
  return error ? { error } : { data };
}

export async function getRun(runId) {
  const { data, error } = await supabase
    .from('digest_runs')
    .select('*')
    .eq('run_id', runId)
    .single();
  return error ? { error } : { data };
}

export async function upsertRun(run) {
  const { data, error } = await supabase.from('digest_runs').upsert(run);
  return error ? { error } : { data };
}

// --- Market data -----------------------------------------------------------

export async function listMarketData(runId, kind) {
  let q = supabase.from('market_data').select('*').eq('run_id', runId);
  if (kind) q = q.eq('kind', kind);
  const { data, error } = await q;
  return error ? { error } : { data };
}

export async function upsertMarketData(rows) {
  const { error } = await supabase.from('market_data').upsert(rows);
  return error ? { error } : null;
}

// --- Performers ------------------------------------------------------------

export async function listPerformers(runId, region) {
  let q = supabase.from('performers').select('*').eq('run_id', runId);
  if (region) q = q.eq('region', region);
  const { data, error } = await q;
  return error ? { error } : { data };
}

export async function upsertPerformers(rows) {
  const { error } = await supabase.from('performers').upsert(rows);
  return error ? { error } : null;
}

// --- Capital raises --------------------------------------------------------

export async function listCapitalRaises(runId) {
  const { data, error } = await supabase
    .from('capital_raises')
    .select('*')
    .eq('run_id', runId)
    .order('region');
  return error ? { error } : { data };
}

export async function upsertCapitalRaises(rows) {
  const { error } = await supabase.from('capital_raises').upsert(rows);
  return error ? { error } : null;
}

// --- News ------------------------------------------------------------------

export async function listNews(runId, section, outlet) {
  let q = supabase.from('news').select('*').eq('run_id', runId);
  if (section) q = q.eq('section', section);
  if (outlet) q = q.eq('outlet', outlet);
  const { data, error } = await q;
  return error ? { error } : { data };
}

export async function upsertNews(rows) {
  const { error } = await supabase.from('news').upsert(rows);
  return error ? { error } : null;
}

// --- Weather ---------------------------------------------------------------

export async function getWeather(runId) {
  const { data, error } = await supabase
    .from('weather')
    .select('*')
    .eq('run_id', runId);
  return error ? { error } : { data };
}

export async function upsertWeather(rows) {
  const { error } = await supabase.from('weather').upsert(rows);
  return error ? { error } : null;
}

// --- Saved items (user-owned dynamic content) ------------------------------

export async function listSavedItems() {
  const { data, error } = await supabase
    .from('saved_items')
    .select('*')
    .order('created_at', { ascending: false });
  return error ? { error } : { data };
}

export async function addSavedItem(item) {
  const user = await supabase.auth.getUser();
  if (!user.data?.user) return { error: { message: 'You must be signed in to save items.' } };
  const { data, error } = await supabase.from('saved_items').insert({
    user_id: user.data.user.id,
    ...item,
  }).select().single();
  return error ? { error } : { data };
}

export async function removeSavedItem(id) {
  const { error } = await supabase.from('saved_items').delete().eq('id', id);
  return error ? { error } : null;
}
