# Video Studio's spoken steps: reads lines from the step window (vs_prompt.py) and says each one with Windows'
# own voice, then prints "said" so the voice control doesn't take the spoken words for yours.
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$voice = New-Object System.Speech.Synthesis.SpeechSynthesizer
$voice.Rate = 0
$voice.Volume = 100
[Console]::Out.WriteLine('ready')
[Console]::Out.Flush()
while ($true) {
    $line = [Console]::In.ReadLine()
    if ($null -eq $line) { break }
    if ($line.Trim() -ne '') { $voice.Speak($line) }
    [Console]::Out.WriteLine('said')
    [Console]::Out.Flush()
}
