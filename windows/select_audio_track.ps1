param(
    [string]$YtdlpExe,
    [string]$Url,
    [string]$Title,
    [string]$DialogTitle,
    [string]$PromptText,
    [string]$FallbackLabel,
    [string]$UserAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    [string]$LangChoice = "EN",
    [string]$CacheFile,
    [ValidateSet("Dialog", "Prefetch", "PageWorker", "YtdlpWorker")]
    [string]$Mode = "Dialog",
    [string]$WorkerOutputFile
)

function Get-YouTubeVideoId {
    param([string]$VideoUrl)

    if ($VideoUrl -match '(?:v=|youtu\.be/|/shorts/)([a-zA-Z0-9_-]{11})') {
        return $matches[1]
    }

    return $null
}

function Get-AudioLanguagesFromYouTubePage {
    param(
        [string]$VideoUrl,
        [string]$Agent,
        [string]$LanguageChoice
    )

    $videoId = Get-YouTubeVideoId -VideoUrl $VideoUrl
    if (-not $videoId) {
        return @()
    }

    $acceptLanguage = "en-US,en"
    if ($LanguageChoice -eq "DE") {
        $acceptLanguage = "de-DE,de;q=0.9,en;q=0.8"
    }

    try {
        $response = Invoke-WebRequest -Uri "https://www.youtube.com/watch?v=$videoId" -UseBasicParsing `
            -Headers @{
                "User-Agent"      = $Agent
                "Accept-Language" = $acceptLanguage
            }
        $html = $response.Content
    }
    catch {
        return @()
    }

    if ($html -notmatch 'ytInitialPlayerResponse\s*=\s*(\{.+?\})\s*;') {
        return @()
    }

    try {
        $data = $matches[1] | ConvertFrom-Json
    }
    catch {
        return @()
    }

    $tracks = @{}

    foreach ($format in $data.streamingData.adaptiveFormats) {
        if ($format.mimeType -notmatch 'audio') {
            continue
        }

        $audioTrack = $format.audioTrack
        if (-not $audioTrack -or -not $audioTrack.id) {
            continue
        }

        $code = ($audioTrack.id -split '\.')[0]
        $label = if ($audioTrack.displayName) { $audioTrack.displayName } else { $code }
        $isOriginal = ($label -match '(?i)original')
        $isDefault = [bool]$audioTrack.audioIsDefault

        if (-not $tracks.ContainsKey($code)) {
            $tracks[$code] = [PSCustomObject]@{
                Code       = $code
                Label      = $label
                IsOriginal = $isOriginal
                IsDefault  = $isDefault
            }
        }
        else {
            if ($isOriginal) { $tracks[$code].IsOriginal = $true }
            if ($isDefault) { $tracks[$code].IsDefault = $true }
        }
    }

    return $tracks.Values
}

function Get-AudioLanguagesFromYtdlp {
    param([string]$Ytdlp, [string]$VideoUrl)

    $json = & $Ytdlp --no-warnings --extractor-args "youtube:player_client=default,web_embedded" -J $VideoUrl 2>$null
    if (-not $json) {
        return @()
    }

    try {
        $data = $json | ConvertFrom-Json
    }
    catch {
        return @()
    }

    $tracks = @{}

    foreach ($format in $data.formats) {
        if ($format.acodec -eq "none" -or $format.vcodec -ne "none") {
            continue
        }

        $lang = if ($format.language) { $format.language } else { "und" }
        $code = ($lang -split '-')[0].ToLower()
        if ($code -eq "und") {
            continue
        }

        $note = if ($format.format_note) { $format.format_note } else { "" }
        $label = if ($note) { ($note -split ',')[0].Trim() } else { $code }
        $isOriginal = ($note -match '(?i)original')
        $isDefault = ($note -match '(?i)default')
        $preference = if ($format.language_preference) { [int]$format.language_preference } else { -1 }

        if (-not $tracks.ContainsKey($code) -or $preference -gt $tracks[$code].Preference) {
            $tracks[$code] = [PSCustomObject]@{
                Code       = $code
                Label      = $label
                IsOriginal = $isOriginal
                IsDefault  = $isDefault
                Preference = $preference
            }
        }
        else {
            if ($isOriginal) { $tracks[$code].IsOriginal = $true }
            if ($isDefault) { $tracks[$code].IsDefault = $true }
        }
    }

    return $tracks.Values
}

function Order-AudioLanguageOptions {
    param(
        [array]$Tracks,
        [string]$Fallback
    )

    if (-not $Tracks -or $Tracks.Count -eq 0) {
        return ,@([PSCustomObject]@{
            Code       = "default"
            Label      = $Fallback
            IsSelected = $true
        })
    }

    $unique = @{}
    foreach ($track in $Tracks) {
        if (-not $unique.ContainsKey($track.Code)) {
            $unique[$track.Code] = $track
        }
    }

    $primary = ($unique.Values | Where-Object { $_.IsOriginal } | Select-Object -First 1).Code
    if (-not $primary) {
        $primary = ($unique.Values | Where-Object { $_.IsDefault } | Select-Object -First 1).Code
    }
    if (-not $primary) {
        $primary = ($unique.Values | Sort-Object -Property @{ Expression = { $_.Preference }; Descending = $true } | Select-Object -First 1).Code
    }
    if (-not $primary) {
        $primary = ($unique.Keys | Sort-Object | Select-Object -First 1)
    }

    $ordered = @()
    $ordered += [PSCustomObject]@{
        Code       = $primary
        Label      = $unique[$primary].Label
        IsSelected = $true
    }

    foreach ($code in ($unique.Keys | Sort-Object)) {
        if ($code -eq $primary) {
            continue
        }

        $ordered += [PSCustomObject]@{
            Code       = $code
            Label      = $unique[$code].Label
            IsSelected = $false
        }
    }

    return $ordered
}

function Write-AudioLanguageCache {
    param(
        [array]$Options,
        [string]$Path
    )

    $lines = foreach ($option in $Options) {
        $selected = if ($option.IsSelected) { 1 } else { 0 }
        "{0}|{1}|{2}" -f $option.Code, $option.Label, $selected
    }

    Set-Content -Path $Path -Value $lines -Encoding UTF8
}

function Read-AudioLanguageCache {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        return @()
    }

    return Get-Content -Path $Path -Encoding UTF8 | ForEach-Object {
        $parts = $_ -split '\|', 3
        if ($parts.Count -lt 2) {
            return
        }

        [PSCustomObject]@{
            Code       = $parts[0]
            Label      = $parts[1]
            IsSelected = ($parts.Count -gt 2 -and $parts[2] -eq "1")
        }
    }
}

function Get-AudioLanguageOptions {
    param(
        [string]$Ytdlp,
        [string]$VideoUrl,
        [string]$Agent,
        [string]$LanguageChoice,
        [string]$Fallback
    )

    $pageTracks = Get-AudioLanguagesFromYouTubePage -VideoUrl $VideoUrl -Agent $Agent -LanguageChoice $LanguageChoice
    if ($pageTracks -and $pageTracks.Count -gt 0) {
        return Order-AudioLanguageOptions -Tracks $pageTracks -Fallback $Fallback
    }

    $ytdlpTracks = Get-AudioLanguagesFromYtdlp -Ytdlp $Ytdlp -VideoUrl $VideoUrl
    return Order-AudioLanguageOptions -Tracks $ytdlpTracks -Fallback $Fallback
}

function Get-AudioLanguageOptionsParallel {
    param(
        [string]$Ytdlp,
        [string]$VideoUrl,
        [string]$Agent,
        [string]$LanguageChoice,
        [string]$Fallback
    )

    return Get-AudioLanguageOptions -Ytdlp $Ytdlp -VideoUrl $VideoUrl -Agent $Agent `
        -LanguageChoice $LanguageChoice -Fallback $Fallback
}

if ($Mode -eq "PageWorker") {
    $tracks = Get-AudioLanguagesFromYouTubePage -VideoUrl $Url -Agent $UserAgent -LanguageChoice $LangChoice
    $tracks | Export-Clixml -Path $WorkerOutputFile
    exit 0
}

if ($Mode -eq "YtdlpWorker") {
    $tracks = Get-AudioLanguagesFromYtdlp -Ytdlp $YtdlpExe -VideoUrl $Url
    $tracks | Export-Clixml -Path $WorkerOutputFile
    exit 0
}

if ($Mode -eq "Prefetch") {
    $options = Get-AudioLanguageOptionsParallel -Ytdlp $YtdlpExe -VideoUrl $Url -Agent $UserAgent `
        -LanguageChoice $LangChoice -Fallback $FallbackLabel
    Write-AudioLanguageCache -Options $options -Path $CacheFile
    exit 0
}

$options = @()
if ($CacheFile) {
    $deadline = (Get-Date).AddSeconds(45)
    while (-not (Test-Path $CacheFile) -and (Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 150
    }

    $options = Read-AudioLanguageCache -Path $CacheFile
}

if (-not $options -or $options.Count -eq 0) {
    $options = Get-AudioLanguageOptionsParallel -Ytdlp $YtdlpExe -VideoUrl $Url -Agent $UserAgent `
        -LanguageChoice $LangChoice -Fallback $FallbackLabel
}

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$form = New-Object System.Windows.Forms.Form
$form.Text = $DialogTitle
$form.Width = 460
$form.StartPosition = "CenterScreen"
$form.TopMost = $true
$form.FormBorderStyle = "FixedDialog"
$form.MaximizeBox = $false

$titleLabel = New-Object System.Windows.Forms.Label
$titleLabel.Text = $Title
$titleLabel.Location = New-Object System.Drawing.Point(10, 10)
$titleLabel.Size = New-Object System.Drawing.Size(420, 40)
$titleLabel.Font = New-Object System.Drawing.Font("Segoe UI", 9, [System.Drawing.FontStyle]::Bold)
$form.Controls.Add($titleLabel)

$promptLabel = New-Object System.Windows.Forms.Label
$promptLabel.Text = $PromptText
$promptLabel.Location = New-Object System.Drawing.Point(20, 58)
$promptLabel.AutoSize = $true
$form.Controls.Add($promptLabel)

$yPos = 85
$radioButtons = @()

foreach ($option in $options) {
    $radio = New-Object System.Windows.Forms.RadioButton
    $radio.Text = $option.Label
    $radio.Tag = $option.Code
    $radio.Location = New-Object System.Drawing.Point(30, $yPos)
    $radio.Width = 390
    $radio.Checked = $option.IsSelected
    $form.Controls.Add($radio)
    $radioButtons += $radio
    $yPos += 28
}

if ($radioButtons.Count -gt 0 -and -not ($radioButtons | Where-Object { $_.Checked })) {
    $radioButtons[0].Checked = $true
}

$button = New-Object System.Windows.Forms.Button
$button.Text = "OK"
$button.Location = New-Object System.Drawing.Point(170, ($yPos + 10))
$button.Width = 100
$button.Height = 35
$button.DialogResult = [System.Windows.Forms.DialogResult]::OK
$form.Controls.Add($button)
$form.AcceptButton = $button
$form.Height = [Math]::Min(700, $yPos + 90)

$result = $form.ShowDialog()

if ($result -eq [System.Windows.Forms.DialogResult]::OK) {
    $selected = $radioButtons | Where-Object { $_.Checked } | Select-Object -First 1
    if ($selected) {
        Write-Output $selected.Tag
    }
}
else {
    Write-Output "CANCELED"
}

$form.Dispose()

if ($CacheFile -and (Test-Path $CacheFile)) {
    Remove-Item -Path $CacheFile -Force -ErrorAction SilentlyContinue
}
