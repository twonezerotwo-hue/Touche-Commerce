<#
.SYNOPSIS
    Live Stage 1A verification against a running API (:8000) and web shell (:3000).

.DESCRIPTION
    Exercises the real HTTP surface with cookie handling and redirects disabled,
    so session cookies, rotation, CSRF, Origin validation and the same-origin
    proxy are verified exactly as a browser would experience them. No browser
    automation is required and no browser automation is claimed.

    The script never prints the password. It fails with a non-zero exit code if
    any check fails, and it does not mutate companies, users or memberships.

.PARAMETER Email
    Administrator email to sign in with (prompted when omitted).

.PARAMETER PasswordStdin
    Read the password from standard input instead of a hidden prompt (automation).

.PARAMETER ApiBase
    API origin (default http://127.0.0.1:8000).

.PARAMETER WebBase
    Web shell origin (default http://localhost:3000).

.EXAMPLE
    scripts\verify-identity.ps1 -Email amina@touche.example
#>
param(
    [string] $Email,
    [switch] $PasswordStdin,
    [string] $ApiBase = 'http://127.0.0.1:8000',
    [string] $WebBase = 'http://localhost:3000'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Windows PowerShell 5.1 does not load System.Net.Http by default.
Add-Type -AssemblyName System.Net.Http

$script:Failures = [System.Collections.Generic.List[string]]::new()

function Write-Check {
    param([string] $Name, [bool] $Passed, [string] $Detail = '')
    if ($Passed) {
        Write-Host ("  [pass] {0}{1}" -f $Name, $(if ($Detail) { " -> $Detail" } else { '' })) -ForegroundColor Green
    }
    else {
        Write-Host ("  [FAIL] {0}{1}" -f $Name, $(if ($Detail) { " -> $Detail" } else { '' })) -ForegroundColor Red
        $script:Failures.Add($Name)
    }
}

function New-HttpSession {
    $handler = [System.Net.Http.HttpClientHandler]::new()
    $handler.UseCookies = $true
    $handler.CookieContainer = [System.Net.CookieContainer]::new()
    $handler.AllowAutoRedirect = $false
    $client = [System.Net.Http.HttpClient]::new($handler)
    $client.Timeout = [TimeSpan]::FromSeconds(20)
    return [pscustomobject]@{ Client = $client; Cookies = $handler.CookieContainer }
}

function Send-Request {
    param(
        [Parameter(Mandatory = $true)] $Session,
        [Parameter(Mandatory = $true)] [string] $Method,
        [Parameter(Mandatory = $true)] [string] $Url,
        [string] $Body,
        [string] $CsrfToken,
        [string] $Origin
    )

    $request = [System.Net.Http.HttpRequestMessage]::new([System.Net.Http.HttpMethod]::new($Method), $Url)
    if ($Origin) { [void]$request.Headers.TryAddWithoutValidation('Origin', $Origin) }
    if ($CsrfToken) { [void]$request.Headers.TryAddWithoutValidation('X-CSRF-Token', $CsrfToken) }
    [void]$request.Headers.TryAddWithoutValidation('Accept', 'application/json')
    if ($Body) {
        $content = [System.Net.Http.StringContent]::new($Body, [System.Text.Encoding]::UTF8, 'application/json')
        $request.Content = $content
    }

    $response = $Session.Client.SendAsync($request).GetAwaiter().GetResult()
    $text = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
    $setCookie = @()
    if ($response.Headers.Contains('Set-Cookie')) { $setCookie = @($response.Headers.GetValues('Set-Cookie')) }

    return [pscustomobject]@{
        Status    = [int]$response.StatusCode
        Body      = $text
        SetCookie = ($setCookie -join "`n")
        Json      = $(if ($text) { try { $text | ConvertFrom-Json } catch { $null } } else { $null })
        Location  = $(if ($response.Headers.Location) { $response.Headers.Location.ToString() } else { $null })
    }
}

function Get-CookieValue {
    param($Session, [string] $Origin, [string] $Name)
    $uri = [Uri]::new($Origin)
    $cookies = $Session.Cookies.GetCookies($uri)
    foreach ($cookie in $cookies) {
        if ($cookie.Name -eq $Name) { return $cookie.Value }
    }
    return $null
}

function Get-ErrorCode {
    param($Response)
    if ($Response.Json -and $Response.Json.error) { return [string]$Response.Json.error.code }
    return ''
}

# ---------------------------------------------------------------------------
# Credentials (never echoed, never stored)
# ---------------------------------------------------------------------------
if (-not $Email) {
    $Email = (Read-Host 'Administrator email').Trim()
}
if ($PasswordStdin) {
    $password = [Console]::In.ReadLine()
}
else {
    $secure = Read-Host -AsSecureString 'Password'
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { $password = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
}
if ([string]::IsNullOrWhiteSpace($password)) { throw 'A password is required.' }

$origin = 'http://localhost:3000'
$api = $ApiBase.TrimEnd('/')
$web = $WebBase.TrimEnd('/')

Write-Host ''
Write-Host '==> Direct API checks' -ForegroundColor Cyan
$apiSession = New-HttpSession

$live = Send-Request -Session $apiSession -Method GET -Url "$api/api/v1/health/live"
Write-Check 'GET /health/live returns 200' ($live.Status -eq 200) "HTTP $($live.Status)"

$ready = Send-Request -Session $apiSession -Method GET -Url "$api/api/v1/health/ready"
Write-Check 'GET /health/ready returns ready' ($ready.Status -eq 200 -and $ready.Json.status -eq 'ready') "HTTP $($ready.Status)"

$noOrigin = Send-Request -Session $apiSession -Method POST -Url "$api/api/v1/auth/login" `
    -Body (@{ email = $Email; password = $password } | ConvertTo-Json -Compress)
Write-Check 'login without Origin is rejected' ($noOrigin.Status -eq 403 -and (Get-ErrorCode $noOrigin) -eq 'ORIGIN_REJECTED') "HTTP $($noOrigin.Status) $(Get-ErrorCode $noOrigin)"

$badLoginAttempt = New-HttpSession
$bad = Send-Request -Session $badLoginAttempt -Method POST -Url "$api/api/v1/auth/login" `
    -Origin $origin -Body (@{ email = $Email; password = 'definitely-not-the-password' } | ConvertTo-Json -Compress)
Write-Check 'invalid credentials return the generic 401' ($bad.Status -eq 401 -and $bad.Json.error.message -eq 'Email or password is incorrect.') "HTTP $($bad.Status)"

$login = Send-Request -Session $apiSession -Method POST -Url "$api/api/v1/auth/login" `
    -Origin $origin -Body (@{ email = $Email; password = $password } | ConvertTo-Json -Compress)
Write-Check 'login succeeds' ($login.Status -eq 200) "HTTP $($login.Status)"
Write-Check 'session cookie is HttpOnly' ($login.SetCookie -match 'HttpOnly')
Write-Check 'session cookie is SameSite=Lax' ($login.SetCookie -match 'SameSite=Lax')
Write-Check 'login body carries no token or password hash' (
    $login.Body -notmatch 'password_hash' -and $login.Body -notmatch "`"token`""
)
Write-Check 'login body exposes memberships' ($login.Json.memberships.Count -ge 1) "$($login.Json.memberships.Count) membership(s)"
$csrf = [string]$login.Json.session.csrf_token
$firstCompany = if ($login.Json.session.company) { $login.Json.session.company.company_id } else { $login.Json.memberships[0].company_id }
Write-Check 'CSRF token issued' (-not [string]::IsNullOrWhiteSpace($csrf))

$me = Send-Request -Session $apiSession -Method GET -Url "$api/api/v1/auth/me"
Write-Check 'GET /auth/me returns the actor' ($me.Status -eq 200 -and $me.Json.user.email -eq $Email) "HTTP $($me.Status)"

$companies = Send-Request -Session $apiSession -Method GET -Url "$api/api/v1/companies"
Write-Check 'GET /companies lists only memberships' ($companies.Status -eq 200 -and $companies.Json.companies.Count -eq $login.Json.memberships.Count) "$($companies.Json.companies.Count) company(ies)"

$csrfMissing = Send-Request -Session $apiSession -Method POST -Url "$api/api/v1/session/company" `
    -Origin $origin -Body (@{ company_id = $firstCompany } | ConvertTo-Json -Compress)
Write-Check 'company switch without CSRF is rejected' ($csrfMissing.Status -eq 403 -and (Get-ErrorCode $csrfMissing) -eq 'CSRF_REJECTED') "HTTP $($csrfMissing.Status) $(Get-ErrorCode $csrfMissing)"

$tokenBefore = Get-CookieValue -Session $apiSession -Origin $api -Name 'touche_session'
$switch = Send-Request -Session $apiSession -Method POST -Url "$api/api/v1/session/company" `
    -Origin $origin -CsrfToken $csrf -Body (@{ company_id = $firstCompany } | ConvertTo-Json -Compress)
$tokenAfter = Get-CookieValue -Session $apiSession -Origin $api -Name 'touche_session'
Write-Check 'company switch succeeds' ($switch.Status -eq 200 -and $switch.Json.session.company.company_id -eq $firstCompany) "HTTP $($switch.Status)"
Write-Check 'session token rotated on switch' ($tokenBefore -and $tokenAfter -and $tokenBefore -ne $tokenAfter)
$csrf = [string]$switch.Json.session.csrf_token

$foreign = Send-Request -Session $apiSession -Method POST -Url "$api/api/v1/session/company" `
    -Origin $origin -CsrfToken $csrf -Body (@{ company_id = [guid]::NewGuid().ToString() } | ConvertTo-Json -Compress)
Write-Check 'switch to a non-member company is forbidden' ($foreign.Status -eq 403 -and (Get-ErrorCode $foreign) -eq 'FORBIDDEN') "HTTP $($foreign.Status) $(Get-ErrorCode $foreign)"

$logout = Send-Request -Session $apiSession -Method POST -Url "$api/api/v1/auth/logout" -Origin $origin -CsrfToken $csrf
Write-Check 'logout succeeds' ($logout.Status -eq 200) "HTTP $($logout.Status)"

$afterLogout = Send-Request -Session $apiSession -Method GET -Url "$api/api/v1/auth/me"
Write-Check 'session is invalid after logout' ($afterLogout.Status -eq 401) "HTTP $($afterLogout.Status)"


Write-Host ''
Write-Host '==> Same-origin proxy and web shell' -ForegroundColor Cyan
$webSession = New-HttpSession

$loginPage = Send-Request -Session $webSession -Method GET -Url "$web/login"
Write-Check 'GET /login renders' ($loginPage.Status -eq 200 -and $loginPage.Body -match 'Sign in') "HTTP $($loginPage.Status)"

$protected = Send-Request -Session $webSession -Method GET -Url "$web/account"
Write-Check 'unauthenticated /account redirects to login' (
    $protected.Status -in 302, 303, 307, 308 -and $protected.Location -match '/login'
) "HTTP $($protected.Status) -> $($protected.Location)"

$publicStatus = Send-Request -Session $webSession -Method GET -Url "$web/status"
Write-Check 'public /status renders without a session' ($publicStatus.Status -eq 200 -and $publicStatus.Body -match 'System status') "HTTP $($publicStatus.Status)"

$proxyLogin = Send-Request -Session $webSession -Method POST -Url "$web/api/v1/auth/login" `
    -Origin $origin -Body (@{ email = $Email; password = $password } | ConvertTo-Json -Compress)
Write-Check 'login through the same-origin proxy succeeds' ($proxyLogin.Status -eq 200) "HTTP $($proxyLogin.Status)"
Write-Check 'proxy forwards Set-Cookie intact' ($proxyLogin.SetCookie -match 'touche_session=' -and $proxyLogin.SetCookie -match 'HttpOnly')
Write-Check 'proxy login answer contains no token' ($proxyLogin.Body -notmatch 'password_hash' -and $proxyLogin.Body -notmatch "`"token`"")
$webCsrf = [string]$proxyLogin.Json.session.csrf_token
$webCompany = if ($proxyLogin.Json.session.company) { $proxyLogin.Json.session.company.company_id } else { $proxyLogin.Json.memberships[0].company_id }

# With more than one membership the backend deliberately leaves the company
# unset, and the shell must send the visitor to the selection screen first.
if (-not $proxyLogin.Json.session.company) {
    $needsCompany = Send-Request -Session $webSession -Method GET -Url "$web/"
    Write-Check 'multi-company session is sent to company selection' (
        $needsCompany.Status -in 302, 303, 307, 308 -and $needsCompany.Location -match '/select-company'
    ) "HTTP $($needsCompany.Status) -> $($needsCompany.Location)"

    $proxySwitch = Send-Request -Session $webSession -Method POST -Url "$web/api/v1/session/company" `
        -Origin $origin -CsrfToken $webCsrf -Body (@{ company_id = $webCompany } | ConvertTo-Json -Compress)
    Write-Check 'company switch works through the proxy' ($proxySwitch.Status -eq 200) "HTTP $($proxySwitch.Status)"
    $webCsrf = [string]$proxySwitch.Json.session.csrf_token
}

$dashboard = Send-Request -Session $webSession -Method GET -Url "$web/"
$displayName = [string]$proxyLogin.Json.user.display_name
Write-Check 'authenticated dashboard renders the signed-in user' ($dashboard.Status -eq 200 -and $dashboard.Body -match [regex]::Escape($displayName)) "HTTP $($dashboard.Status)"

$accountPage = Send-Request -Session $webSession -Method GET -Url "$web/account"
Write-Check 'authenticated /account renders' ($accountPage.Status -eq 200 -and $accountPage.Body -match 'Profile &amp; access|Profile & access') "HTTP $($accountPage.Status)"
$webCsrf = [string]$proxySwitch.Json.session.csrf_token
$csrfRejected = Send-Request -Session $webSession -Method POST -Url "$web/api/v1/auth/logout" -Origin $origin
Write-Check 'proxy preserves CSRF rejection' ($csrfRejected.Status -eq 403 -and (Get-ErrorCode $csrfRejected) -eq 'CSRF_REJECTED') "HTTP $($csrfRejected.Status) $(Get-ErrorCode $csrfRejected)"

$proxyLogout = Send-Request -Session $webSession -Method POST -Url "$web/api/v1/auth/logout" -Origin $origin -CsrfToken $webCsrf
Write-Check 'logout through the proxy succeeds' ($proxyLogout.Status -eq 200) "HTTP $($proxyLogout.Status)"

$afterProxyLogout = Send-Request -Session $webSession -Method GET -Url "$web/"
Write-Check 'dashboard redirects to login after logout' (
    $afterProxyLogout.Status -in 302, 303, 307, 308 -and $afterProxyLogout.Location -match '/login'
) "HTTP $($afterProxyLogout.Status) -> $($afterProxyLogout.Location)"

Write-Host ''
if ($script:Failures.Count -gt 0) {
    Write-Host ("IDENTITY VERIFICATION FAILED: {0}" -f ($script:Failures -join ', ')) -ForegroundColor Red
    exit 1
}
Write-Host 'All identity checks passed.' -ForegroundColor Green
exit 0

