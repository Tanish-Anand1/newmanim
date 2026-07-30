export default function handler(req, res) {
  res.status(200).json({
    BACKEND_URL: process.env.BACKEND_URL || 'http://localhost:8000',
    SUPABASE_URL: process.env.SUPABASE_URL || 'https://ykojwrclyhyyqburnbyh.supabase.co',
    SUPABASE_ANON_KEY: process.env.SUPABASE_ANON_KEY || 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inlrb2p3cmNseWh5eXFidXJuYnloIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODQwNjU4NjgsImV4cCI6MjA5OTY0MTg2OH0.RpLfPVoGxPLkFDM05BatqbVNTs02Ci_hs8XOj6O1cMI'
  });
}
