Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

# === Configuration ===
$boosterMailExe = "C:\Users\yvanb\AppData\Local\BoosterMail\BoosterMail.exe"
$startV1Bat = "C:\Users\yvanb\OneDrive\Desktop\EasyMail\V1_outlook\start_v1.bat"
$outlookProcesses = @("olk", "outlook")

# === Fonction : Outlook tourne ? ===
function Test-OutlookRunning {
    foreach ($name in $outlookProcesses) {
        if (Get-Process -Name $name -ErrorAction SilentlyContinue) { return $true }
    }
    return $false
}

# === Attendre Outlook (invisible, poll toutes les 1s) ===
while (-not (Test-OutlookRunning)) {
    Start-Sleep -Seconds 1
}

# === Creer la popup ===
$form = New-Object System.Windows.Forms.Form
$form.Text = "BoosterMail"
$form.Size = New-Object System.Drawing.Size(340, 200)
$form.StartPosition = "CenterScreen"
$form.FormBorderStyle = "FixedDialog"
$form.MaximizeBox = $false
$form.MinimizeBox = $false
$form.TopMost = $true
$form.BackColor = [System.Drawing.Color]::White

# Logo
$lblLogo = New-Object System.Windows.Forms.Label
$lblLogo.Text = [char]0x2709 + " BoosterMail"
$lblLogo.Font = New-Object System.Drawing.Font("Segoe UI", 16, [System.Drawing.FontStyle]::Bold)
$lblLogo.ForeColor = [System.Drawing.Color]::FromArgb(15, 108, 189)
$lblLogo.AutoSize = $true
$lblLogo.Location = New-Object System.Drawing.Point(70, 25)
$form.Controls.Add($lblLogo)

# Sous-titre
$lblSub = New-Object System.Windows.Forms.Label
$lblSub.Text = "Assistant email intelligent"
$lblSub.Font = New-Object System.Drawing.Font("Segoe UI", 9)
$lblSub.ForeColor = [System.Drawing.Color]::Gray
$lblSub.AutoSize = $true
$lblSub.Location = New-Object System.Drawing.Point(90, 60)
$form.Controls.Add($lblSub)

# Bouton Annuler
$btnNo = New-Object System.Windows.Forms.Button
$btnNo.Text = "Annuler"
$btnNo.Size = New-Object System.Drawing.Size(120, 35)
$btnNo.Location = New-Object System.Drawing.Point(30, 110)
$btnNo.FlatStyle = "Flat"
$btnNo.Font = New-Object System.Drawing.Font("Segoe UI", 10)
$btnNo.ForeColor = [System.Drawing.Color]::Gray
$btnNo.Add_Click({ $form.Close() })
$form.Controls.Add($btnNo)

# Bouton Lancer
$btnYes = New-Object System.Windows.Forms.Button
$btnYes.Text = "Lancer BoosterMail"
$btnYes.Size = New-Object System.Drawing.Size(150, 35)
$btnYes.Location = New-Object System.Drawing.Point(160, 110)
$btnYes.FlatStyle = "Flat"
$btnYes.Font = New-Object System.Drawing.Font("Segoe UI", 10, [System.Drawing.FontStyle]::Bold)
$btnYes.BackColor = [System.Drawing.Color]::FromArgb(15, 108, 189)
$btnYes.ForeColor = [System.Drawing.Color]::White
$btnYes.Add_Click({
    # Lancer BoosterMail.exe (overlay PyQt)
    Start-Process -FilePath $boosterMailExe -WindowStyle Hidden
    # Lancer le backend + companion
    Start-Process -FilePath $startV1Bat -WindowStyle Hidden
    # Fermer le launcher
    $form.Close()
})
$form.Controls.Add($btnYes)

# Afficher
$form.ShowDialog() | Out-Null
