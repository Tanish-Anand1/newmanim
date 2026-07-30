$root=Join-Path $PSScriptRoot 'multi_scene_render'
$final=Join-Path $root 'final\vivacity_three_chapter_final.mp4'
if(-not(Test-Path -LiteralPath $final)){throw "Missing final output $final"}
. (Join-Path $PSScriptRoot 'verify_stitch_ps51_a.ps1')
. (Join-Path $PSScriptRoot 'verify_stitch_ps51_b.ps1')
