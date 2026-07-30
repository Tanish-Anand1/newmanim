$root=Join-Path $PSScriptRoot 'multi_scene_render'
$out=Join-Path $root 'final'
$python=Join-Path $PSScriptRoot 'manim-env\Scripts\python.exe'
New-Item -ItemType Directory -Force -Path $root,$out | Out-Null
$specs=@(
 @{s='scene_chapter1_one_die.py';c='OneDieChapter';d='chapter1';a='chapter1_audio.mp3'},
 @{s='scene_chapter2_two_dice.py';c='TwoDiceChapter';d='chapter2';a='chapter2_audio.mp3'},
 @{s='scene_chapter3_many_dice.py';c='ManyDiceChapter';d='chapter3';a='chapter3_audio.mp3'}
)
foreach($x in $specs){
 $src=Join-Path $PSScriptRoot $x.s; $media=Join-Path $root $x.d
 if(-not(Test-Path -LiteralPath $src)){throw "Missing scene $src"}
 & $python -m manim -qh --disable_caching --resolution 1920,1080 --frame_rate 60 --media_dir $media $src $x.c
 if($LASTEXITCODE -ne 0){throw "Render failed $($x.c)"}
 $x.v=Get-ChildItem -Recurse -File $media -Filter "$($x.c).mp4" | Where-Object {$_.FullName -notlike '*partial_movie_files*'} | Select-Object -First 1 -ExpandProperty FullName
 $x.ap=Join-Path $PSScriptRoot "multi_scene_audio\$($x.a)"
 if(-not $x.v -or -not(Test-Path -LiteralPath $x.ap)){throw "Missing media $($x.c)"}
}
