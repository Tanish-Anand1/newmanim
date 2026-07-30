$frames=Join-Path $root 'final\boundary_frames';New-Item -ItemType Directory -Force -Path $frames|Out-Null
& ffmpeg -y -ss $b1 -i $final -frames:v 1 (Join-Path $frames 'chapter1_to_chapter2_midfade.png')
& ffmpeg -y -ss $b2 -i $final -frames:v 1 (Join-Path $frames 'chapter2_to_chapter3_midfade.png')
Write-Host "FINAL=$final";Write-Host "CHAPTER_DURATIONS=$($d -join ',')";Write-Host "BOUNDARY_1_MIDFADE=$b1";Write-Host "BOUNDARY_2_MIDFADE=$b2";Write-Host "FRAME_DIR=$frames"
& ffprobe -v error -show_entries stream=codec_type,codec_name,width,height,r_frame_rate,avg_frame_rate,duration -of default=noprint_wrappers=1 $final
