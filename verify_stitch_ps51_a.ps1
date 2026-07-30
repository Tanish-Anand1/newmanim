function Probe([string]$p){return ((& ffprobe -v error -of json -show_streams -show_format -- $p)|ConvertFrom-Json)}
function Duration([string]$p){$q=Probe $p;$s=@($q.streams|Where-Object {$_.codec_type -eq 'video'})[0];if($s.duration){return [double]$s.duration}else{return [double]$q.format.duration}}
$files=@(Get-ChildItem -Recurse -File $root -Filter '*.mp4'|Where-Object {$_.FullName -notlike '*partial_movie_files*' -and $_.FullName -notlike '*final*'}|Sort-Object FullName)
if($files.Count -ne 3){throw "Expected three chapter videos; found $($files.Count)"}
$d=@($files|ForEach-Object {Duration $_.FullName});$fade=.6;$b1=$d[0]-($fade/2);$b2=$d[0]+$d[1]-(3*$fade/2)
