-- Trigger to create a public.users row when a new user signs up in auth.users
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer set search_path = public
as $$
begin
  insert into public.users (id, email, display_name, provider, email_verified)
  values (
    new.id,
    new.email,
    coalesce(new.raw_user_meta_data->>'full_name', coalesce(new.raw_user_meta_data->>'display_name', split_part(new.email, '@', 1))),
    coalesce(new.raw_app_meta_data->>'provider', 'email'),
    true -- Supabase auth handles verification status internally, but we can set this to true to keep it simple or read from new.email_confirmed_at.
  );
  
  -- We also create the default settings row
  insert into public.user_settings (user_id) values (new.id);
  
  return new;
end;
$$;

-- Create the trigger
drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute procedure public.handle_new_user();

-- Make public.users.id reference auth.users.id
alter table public.users
  drop constraint if exists users_id_fkey,
  add constraint users_id_fkey
  foreign key (id) references auth.users(id) on delete cascade;
