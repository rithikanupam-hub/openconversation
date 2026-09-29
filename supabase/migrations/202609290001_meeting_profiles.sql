-- Account-owned preferences only. No recordings, transcripts, voiceprints or billing data.
create table public.meeting_profiles (
 id uuid primary key default gen_random_uuid(),
 user_id uuid not null references auth.users(id) on delete cascade default auth.uid(),
 name text not null check (char_length(trim(name)) between 1 and 80),
 source_language text not null check (source_language in ('auto','it','en','de','fr','es','pt','nl','zh','ja','ko','ru')),
 target_language text not null check (target_language in ('en','it','de','fr','es','pt','zh','ja','ko','ru')),
 meeting_type text not null check (meeting_type in ('room','meet','group')),
 created_at timestamptz not null default now()
);
create index meeting_profiles_user_id_idx on public.meeting_profiles(user_id);
alter table public.meeting_profiles enable row level security;
revoke all on public.meeting_profiles from anon;
grant select,insert,update,delete on public.meeting_profiles to authenticated;
create policy "Read own meeting profiles" on public.meeting_profiles for select to authenticated using ((select auth.uid())=user_id);
create policy "Create own meeting profiles" on public.meeting_profiles for insert to authenticated with check ((select auth.uid())=user_id);
create policy "Update own meeting profiles" on public.meeting_profiles for update to authenticated using ((select auth.uid())=user_id) with check ((select auth.uid())=user_id);
create policy "Delete own meeting profiles" on public.meeting_profiles for delete to authenticated using ((select auth.uid())=user_id);
