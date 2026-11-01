-- CONTRACTS.md §9. Additions beyond §9 are marked; they do not change any column or constraint.
create schema if not exists extensions;
create extension if not exists pgcrypto with schema extensions;

create type public.job_status   as enum ('PENDING','PROCESSING','COMPLETED','FAILED');
create type public.model_origin as enum ('PROCESSING','EDIT');
create type public.edit_status  as enum ('APPLIED','REJECTED','CLARIFICATION','UNDO','REDO');

create table public.users (
  id uuid primary key default gen_random_uuid(),
  clerk_user_id text not null unique,
  email text unique, display_name text,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create table public.projects (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references public.users(id) on delete cascade,
  name varchar(200) not null, description varchar(2000),
  created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index on public.projects(owner_id, created_at desc);
create table public.floorplans (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references public.projects(id) on delete cascade,
  version int not null, original_filename varchar(255) not null,
  storage_key text not null unique, content_type text not null,
  size_bytes bigint not null, checksum_sha256 char(64) not null,
  status public.job_status not null default 'PENDING',
  current_model_version int, warnings jsonb not null default '[]',
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
  unique (project_id, version)
);
create table public.processing_jobs (
  id uuid primary key default gen_random_uuid(),
  floorplan_id uuid not null references public.floorplans(id) on delete cascade,
  status public.job_status not null default 'PENDING',
  attempts int not null default 0, stages jsonb not null default '[]',
  error_message varchar(500), started_at timestamptz, finished_at timestamptz, heartbeat_at timestamptz,
  created_at timestamptz not null default clock_timestamp(), updated_at timestamptz not null default now()
);
create index on public.processing_jobs(status, created_at);
create index on public.processing_jobs(floorplan_id, created_at desc);
create table public.model_edits (
  id uuid primary key default gen_random_uuid(),
  floorplan_id uuid not null references public.floorplans(id) on delete cascade,
  user_id uuid references public.users(id) on delete set null,
  instruction varchar(500), command jsonb, operation text,
  status public.edit_status not null, stage text, error varchar(500), clarification jsonb,
  parent_version int, result_version int,
  created_at timestamptz not null default clock_timestamp()
);
create table public.building_models (
  id uuid primary key default gen_random_uuid(),
  floorplan_id uuid not null references public.floorplans(id) on delete cascade,
  job_id uuid references public.processing_jobs(id) on delete set null,
  edit_id uuid references public.model_edits(id) on delete set null,
  version int not null, origin public.model_origin not null, parent_version int,
  discarded boolean not null default false, data jsonb not null,
  created_at timestamptz not null default clock_timestamp(),
  unique (floorplan_id, version)
);
create table public.processing_artifacts (
  id uuid primary key default gen_random_uuid(),
  floorplan_id uuid not null references public.floorplans(id) on delete cascade,
  job_id uuid not null references public.processing_jobs(id) on delete cascade,
  kind text not null, storage_key text not null unique,
  content_type text not null, size_bytes bigint not null,
  created_at timestamptz not null default now()
);

-- Addition: covering indexes for the foreign keys §9 leaves unindexed (Supabase advisor unindexed_foreign_keys).
create index on public.model_edits(floorplan_id, created_at desc);
create index on public.model_edits(user_id);
create index on public.building_models(job_id);
create index on public.building_models(edit_id);
create index on public.processing_artifacts(floorplan_id, created_at desc);
create index on public.processing_artifacts(job_id);

-- search_path pinned for the Supabase advisor function_search_path_mutable.
create function public.set_updated_at() returns trigger
language plpgsql set search_path = '' as $$
begin
  new.updated_at := now();
  return new;
end $$;
create trigger set_updated_at before update on public.users
  for each row execute function public.set_updated_at();
create trigger set_updated_at before update on public.projects
  for each row execute function public.set_updated_at();
create trigger set_updated_at before update on public.floorplans
  for each row execute function public.set_updated_at();
create trigger set_updated_at before update on public.processing_jobs
  for each row execute function public.set_updated_at();
revoke execute on function public.set_updated_at() from public;

-- RLS ON with NO policies: anon/authenticated get nothing. services/api connects as postgres (bypasses RLS).
alter table public.users enable row level security;
alter table public.projects enable row level security;
alter table public.floorplans enable row level security;
alter table public.processing_jobs enable row level security;
alter table public.model_edits enable row level security;
alter table public.building_models enable row level security;
alter table public.processing_artifacts enable row level security;

-- Plain Postgres (TEST_DATABASE_URL) has no storage schema.
do $$
begin
  if to_regclass('storage.buckets') is not null then
    insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types) values
      ('floorplans', 'floorplans', false, 26214400, array['image/png','image/jpeg','application/pdf']),
      ('artifacts', 'artifacts', false, 52428800, array['image/png','application/json'])
    on conflict (id) do nothing;
  end if;
end $$;
