function Probe([string]$p){return ((& ffprobe -v error -of json -show_streams -show_format -- $p)|ConvertFrom-Json)}
function VideoMeta([string]$p){
 $q=Probe $p; $s=@($q.streams|Where-Object {$_.codec_type -eq 'video'})[0]
 if(-not $s){throw "No video stream $p"}
 if($s.duration){$d=[double]$s.duration}else{$d=[double]$q.format.duration}
 return [pscustomobject]@{p=$p;d=$d;sig="$($s.width)x$($s.height)|$($s.r_frame_rate)|$($s.codec_name)"}
}
function AudioDuration([string]$p){
 $q=Probe $p; $s=@($q.streams|Where-Object {$_.codec_type -eq 'audio'})[0]
 if(-not $s){throw "No audio stream $p"}
 if($s.duration){return [double]$s.duration}else{return [double]$q.format.duration}
}
$v=@($specs|ForEach-Object {VideoMeta $_.v}); $sig=$v[0].sig
for($i=0;$i -lt 3;$i++){
 $ad=AudioDuration $specs[$i].ap
 Write-Host "CHAPTER_$($i+1) VIDEO=$($v[$i].d) SIGNATURE=$($v[$i].sig) AUDIO=$ad"
 if($v[$i].sig -ne $sig){throw 'Chapter signatures differ'}
 if([math]::Abs($ad-$v[$i].d) -gt .2){throw 'Audio/video drift exceeds .2 seconds'}
}
