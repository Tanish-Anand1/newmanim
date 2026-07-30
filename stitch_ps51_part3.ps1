$fade=.6; $o1=$v[0].d-$fade; $o2=$v[0].d+$v[1].d-(2*$fade)
$vo=Join-Path $out 'video_xfade.mp4'; $ao=Join-Path $out 'audio_acrossfade.m4a'; $fo=Join-Path $out 'vivacity_three_chapter_final.mp4'
$vf="[0:v][1:v]xfade=transition=fade:duration=$fade:offset=$o1[v01];[v01][2:v]xfade=transition=fade:duration=$fade:offset=$o2[vout]"
& ffmpeg -y -i $specs[0].v -i $specs[1].v -i $specs[2].v -filter_complex $vf -map '[vout]' -an -c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p -r 60 $vo
if($LASTEXITCODE -ne 0){throw 'Video xfade failed'}
$af="[0:a][1:a]acrossfade=d=$fade:c1=tri:c2=tri[a01];[a01][2:a]acrossfade=d=$fade:c1=tri:c2=tri[aout]"
& ffmpeg -y -i $specs[0].ap -i $specs[1].ap -i $specs[2].ap -filter_complex $af -map '[aout]' -c:a aac -b:a 192k $ao
if($LASTEXITCODE -ne 0){throw 'Audio crossfade failed'}
& ffmpeg -y -i $vo -i $ao -map 0:v:0 -map 1:a:0 -c:v copy -c:a copy -movflags +faststart $fo
if($LASTEXITCODE -ne 0){throw 'Final mux failed'}
Write-Host "OUTPUT=$fo"; Write-Host "OFFSETS=$o1,$o2 FADE=$fade"
& ffprobe -v error -show_entries stream=codec_type,codec_name,width,height,r_frame_rate,avg_frame_rate,duration -of default=noprint_wrappers=1 $fo
