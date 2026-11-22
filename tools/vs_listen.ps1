# Video Studio's voice control for the step window: listens for a few words (next, ready, done, pause, wait,
# go on, continue) with Windows' own offline speech recognition and prints each one it hears, with how sure it
# is. Only these words; nothing is recorded or sent anywhere. vs_prompt.py starts it and reads what it prints.
param([double]$MinConfidence = 0.7)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$culture = New-Object System.Globalization.CultureInfo('en-US')
$engine = New-Object System.Speech.Recognition.SpeechRecognitionEngine($culture)
$words = New-Object System.Speech.Recognition.Choices
$words.Add([string[]]@('next', 'next step', 'ready', 'done', 'pause', 'wait', 'go on', 'continue'))
$grammar = New-Object System.Speech.Recognition.GrammarBuilder($words)
$grammar.Culture = $culture
$engine.LoadGrammar((New-Object System.Speech.Recognition.Grammar($grammar)))
$engine.SetInputToDefaultAudioDevice()
[Console]::Out.WriteLine('listening')
[Console]::Out.Flush()
while ($true) {
    $heard = $engine.Recognize([TimeSpan]::FromSeconds(5))
    if ($null -ne $heard -and $heard.Confidence -ge $MinConfidence) {
        [Console]::Out.WriteLine($heard.Text + '|' + [math]::Round($heard.Confidence, 2))
        [Console]::Out.Flush()
    }
}
