/**
 * Account, company selection, session states, the public status page and the shell words that
 * were still fixed English (Stage 12H). English keeps the wording these screens always had.
 */
export const accountEn = {
  // Roles (stored values: viewer, trader, approver, admin)
  roleViewer: "Viewer",
  roleTrader: "Trader",
  roleApprover: "Approver",
  roleAdmin: "Administrator",

  // Account page
  acctPageTitle: "Account",
  acctEyebrow: "Account",
  acctAuthenticated: "Authenticated",
  acctTitle: "Profile & access",
  acctDescription:
    "Your identity, the companies you may access and the exact permissions carried by the active membership. Permissions are derived from the role on the server, never from the browser.",
  acctIdentity: "Identity",
  acctSignedInProfile: "Signed-in profile",
  acctMemberships: "Memberships",
  acctCompanyAccess: "Company access",
  acctAvailable: "{count} available",
  acctSwitchNote:
    "Switching company rotates your session token and re-issues the cookie. The previous token stops working immediately.",
  acctSecurity: "Security",
  acctSessionPolicy: "Session policy",
  acctEnforced: "Enforced by the API, not the browser",
  acctIdleTerm: "Idle timeout",
  acctIdleDetail: "30 minutes without activity revokes the session.",
  acctAbsoluteTerm: "Absolute timeout",
  acctAbsoluteDetail: "12 hours after sign-in, regardless of activity.",
  acctRevocationTerm: "Revocation",
  acctRevocationDetail:
    "Removing a membership ends every session bound to that company immediately.",
  acctStorageTerm: "Storage",
  acctStorageDetail:
    "The session token lives only in an HttpOnly cookie; nothing is written to localStorage.",

  // Account summary
  sumName: "Name",
  sumEmail: "Email",
  sumStatus: "Account status",
  sumRole: "Role in active company",
  sumNoCompany: "No active company",
  sumActiveCompany: "Active company",
  sumNotSelected: "Not selected",
  sumStarted: "Session started",
  sumLastActivity: "Last activity",
  sumExpiresAbsolute: "Expires (absolute)",
  sumExpiresIdle: "Expires (idle)",
  sumSessionId: "Session id",
  sumPermissions: "Permissions granted by this membership",
  sumNoPermissions: "No permissions apply until a company is selected.",
  sumOrigin: "Session origin: {address}{agent}",
  sumUnknownAddress: "unknown address",

  // Company switcher
  swNoAccessTitle: "No company access",
  swNoAccessBody:
    "Your account has no active company membership. Ask an administrator to grant access.",
  swCurrent: "Current",
  swSwitching: "Switching",
  swSelect: "Select",

  // Sign out
  logoutLabel: "Sign out",
  logoutPending: "Signing out…",

  // Select company
  selPageTitle: "Select company",
  selEyebrow: "Workspace",
  selTitle: "Choose a company",
  selSignedInAs: "Signed in as",
  selIntro: "Sessions are bound to one company at a time; switching rotates your session token.",
  selRevocation:
    "Access is re-checked on every request. If an administrator revokes your membership, the session for that company ends immediately.",

  // Session unavailable
  suBadge: "Session unavailable",
  suTitle: "The API did not answer",
  suHint: "Start the API with {command}, then reload this page. No session state was changed.",
  suBack: "Back to sign in",
  suStatus: "System status",

  // Public status page
  stPageTitle: "System status",
  stEyebrow: "Platform",
  stBadge: "Public · read only",
  stTitle: "System status",
  stDescription:
    "Live connectivity between the web shell, the FastAPI service and PostgreSQL. This page requires no session and shows no user, company or business data.",
  stRendered: "Rendered {time}",
  stRecheck: "Re-check status",
  stRechecking: "Re-checking",
  stApiDownTitle: "API unreachable",
  stApiDownHint: "Start it with scripts\\dev-backend.ps1 and listen on port 8000.",
  stDbDownTitle: "Database not ready",
  stDbDownHint:
    "Start PostgreSQL (scripts\\db\\start-local-postgres.ps1) and apply migrations (scripts\\migrate.ps1).",
  stContractDownTitle: "OpenAPI contract unavailable",
  stContractDownHint: "Regenerate frontend types with scripts\\generate-api-types.ps1.",
  stLivenessEyebrow: "Liveness",
  stLivenessTitle: "FastAPI service",
  stLivenessAnswered: "{service} v{version} answered HTTP {status}.",
  stLivenessFooter: "Liveness never touches PostgreSQL.",
  stReadinessEyebrow: "Readiness",
  stReadinessTitle: "PostgreSQL",
  stReadinessFooter: "Readiness uses the runtime role (no DDL, no BYPASSRLS).",
  stContractEyebrow: "Contract",
  stContractTitle: "Typed API contract",
  stContractPublished: "{count} operations published by {title}.",
  stContractTheApi: "the API",
  stContractFooter: "Generated types are drift-checked in CI.",
  stRowEndpoint: "Endpoint",
  stRowRequestId: "Request ID",
  stRowLatency: "Latency",
  stRowServer: "Server",
  stRowRole: "Role",
  stRowDocument: "Document",
  stRowVersion: "Version",
  stNotReported: "not reported",
  stNoDbCheck: "The readiness response contained no database check.",
  stOperational: "Operational",
  stDegraded: "Degraded",
  stUnreachable: "Unreachable",
  stNeedTitle: "Need to work?",
  stNeedBody:
    "The workspace — deals, documents and settlement — requires a signed-in session scoped to a company membership.",
  stSignIn: "Sign in",
  stFooterApi: "API {url}",
  stFooterSchema: "schema",
  stFooterOpenApi: "OpenAPI {url}",

  // Shell
  shellBreadcrumbAria: "Breadcrumb",
  shellPrimaryAria: "Primary",
  shellHomeAria: "TOUCHE COMMERCE — home",
  importStepsAria: "Steps",
  cpNotesPlaceholder: "Payment terms, incoterms, history…",
  productNamePlaceholder: "Aluminium ingot A7",

  // Failure text this app builds itself (what the API says is shown as received)
  failGeneric: "The request could not be completed.",
  failUnreachable: "Cannot reach the API. Confirm the service is running and try again.",
  failUnreachableAt: "Cannot reach the API at {url}. Confirm FastAPI is running.",
  failTimeout: "The API did not answer within {ms} ms.",
  failUnexpected: "The API returned an unexpected error response.",
  failBadJson: "The API responded with a body that is not valid JSON.",
  failOpenApi: "The OpenAPI document could not be parsed.",
  failSessionHttp: "The API answered HTTP {status} while checking the session.",
  failProxyDown: "The TOUCHE COMMERCE API is not reachable.",

  // Shell
  shellNoMembership: "No membership",
  shellStageLabel: "Stage 6 · AI Trade Director · Read-only, human-approved",
  navPlannedTip: "{description} — planned for {stage}",

  // Document metadata
  metaDefaultTitle: "TOUCHE COMMERCE — Command Center",
  metaDescription: "Independent, premium international trade management.",

  // Pages that do not exist and screens that failed to render
  nfTitle: "Page not found",
  nfBody: "The page you asked for does not exist or has moved. Nothing was changed.",
  nfBack: "Back to the Command Center",
  errTitle: "Something went wrong on this screen",
  errBody:
    "The screen could not be shown. Nothing was changed. Try again, or return to the Command Center.",
  errReference: "Reference: {digest}",
  errRetry: "Try again",
  errHome: "Command Center",
} as const;

export const accountTr: Record<keyof typeof accountEn, string> = {
  roleViewer: "Görüntüleyici",
  roleTrader: "Ticaret yetkilisi",
  roleApprover: "Onaylayıcı",
  roleAdmin: "Yönetici",

  acctPageTitle: "Hesap",
  acctEyebrow: "Hesap",
  acctAuthenticated: "Oturum açık",
  acctTitle: "Profil ve erişim",
  acctDescription:
    "Kimliğiniz, erişebileceğiniz şirketler ve etkin üyeliğin taşıdığı tam yetkiler. Yetkiler tarayıcıdan değil, sunucudaki rolden türetilir.",
  acctIdentity: "Kimlik",
  acctSignedInProfile: "Oturum açan profil",
  acctMemberships: "Üyelikler",
  acctCompanyAccess: "Şirket erişimi",
  acctAvailable: "{count} erişilebilir",
  acctSwitchNote:
    "Şirket değiştirmek oturum belirtecinizi yeniler ve çerezi yeniden düzenler. Önceki belirteç hemen geçersiz olur.",
  acctSecurity: "Güvenlik",
  acctSessionPolicy: "Oturum politikası",
  acctEnforced: "Tarayıcı değil, API uygular",
  acctIdleTerm: "Hareketsizlik süresi",
  acctIdleDetail: "30 dakika işlem yapılmazsa oturum kapatılır.",
  acctAbsoluteTerm: "Mutlak süre",
  acctAbsoluteDetail: "Etkinlikten bağımsız olarak, girişten 12 saat sonra.",
  acctRevocationTerm: "İptal",
  acctRevocationDetail:
    "Bir üyeliğin kaldırılması, o şirkete bağlı tüm oturumları hemen sonlandırır.",
  acctStorageTerm: "Saklama",
  acctStorageDetail:
    "Oturum belirteci yalnızca HttpOnly çerezinde durur; localStorage'a hiçbir şey yazılmaz.",

  sumName: "Ad",
  sumEmail: "E-posta",
  sumStatus: "Hesap durumu",
  sumRole: "Etkin şirketteki rol",
  sumNoCompany: "Etkin şirket yok",
  sumActiveCompany: "Etkin şirket",
  sumNotSelected: "Seçilmedi",
  sumStarted: "Oturum başlangıcı",
  sumLastActivity: "Son etkinlik",
  sumExpiresAbsolute: "Bitiş (mutlak)",
  sumExpiresIdle: "Bitiş (hareketsizlik)",
  sumSessionId: "Oturum kimliği",
  sumPermissions: "Bu üyeliğin verdiği yetkiler",
  sumNoPermissions: "Bir şirket seçilene kadar hiçbir yetki geçerli değildir.",
  sumOrigin: "Oturum kaynağı: {address}{agent}",
  sumUnknownAddress: "bilinmeyen adres",

  swNoAccessTitle: "Şirket erişimi yok",
  swNoAccessBody:
    "Hesabınızın etkin bir şirket üyeliği yok. Bir yöneticiden erişim vermesini isteyin.",
  swCurrent: "Geçerli",
  swSwitching: "Değiştiriliyor",
  swSelect: "Seç",

  logoutLabel: "Çıkış yap",
  logoutPending: "Çıkış yapılıyor…",

  selPageTitle: "Şirket seç",
  selEyebrow: "Çalışma alanı",
  selTitle: "Bir şirket seçin",
  selSignedInAs: "Oturum açan:",
  selIntro:
    "Oturumlar aynı anda tek bir şirkete bağlıdır; şirket değiştirmek oturum belirtecinizi yeniler.",
  selRevocation:
    "Erişim her istekte yeniden denetlenir. Bir yönetici üyeliğinizi kaldırırsa o şirketin oturumu hemen sona erer.",

  suBadge: "Oturum kullanılamıyor",
  suTitle: "API yanıt vermedi",
  suHint:
    "API'yi {command} ile başlatın, sonra bu sayfayı yeniden yükleyin. Hiçbir oturum durumu değişmedi.",
  suBack: "Girişe dön",
  suStatus: "Sistem durumu",

  stPageTitle: "Sistem durumu",
  stEyebrow: "Platform",
  stBadge: "Herkese açık · salt okunur",
  stTitle: "Sistem durumu",
  stDescription:
    "Web arayüzü, FastAPI hizmeti ve PostgreSQL arasındaki canlı bağlantı. Bu sayfa oturum gerektirmez; kullanıcı, şirket veya ticari veri göstermez.",
  stRendered: "Oluşturulma: {time}",
  stRecheck: "Durumu yeniden denetle",
  stRechecking: "Denetleniyor",
  stApiDownTitle: "API'ye ulaşılamıyor",
  stApiDownHint:
    "scripts\\dev-backend.ps1 ile başlatın ve 8000 numaralı bağlantı noktasını dinletin.",
  stDbDownTitle: "Veritabanı hazır değil",
  stDbDownHint:
    "PostgreSQL'i (scripts\\db\\start-local-postgres.ps1) başlatın ve geçişleri (scripts\\migrate.ps1) uygulayın.",
  stContractDownTitle: "OpenAPI sözleşmesi kullanılamıyor",
  stContractDownHint: "Ön yüz tiplerini scripts\\generate-api-types.ps1 ile yeniden üretin.",
  stLivenessEyebrow: "Canlılık",
  stLivenessTitle: "FastAPI hizmeti",
  stLivenessAnswered: "{service} v{version} HTTP {status} ile yanıt verdi.",
  stLivenessFooter: "Canlılık denetimi PostgreSQL'e hiç dokunmaz.",
  stReadinessEyebrow: "Hazırlık",
  stReadinessTitle: "PostgreSQL",
  stReadinessFooter: "Hazırlık denetimi çalışma rolünü kullanır (DDL yok, BYPASSRLS yok).",
  stContractEyebrow: "Sözleşme",
  stContractTitle: "Tiplenmiş API sözleşmesi",
  stContractPublished: "{title} tarafından {count} işlem yayımlanıyor.",
  stContractTheApi: "API",
  stContractFooter: "Üretilen tipler CI'da sapma açısından denetlenir.",
  stRowEndpoint: "Uç nokta",
  stRowRequestId: "İstek kimliği",
  stRowLatency: "Gecikme",
  stRowServer: "Sunucu",
  stRowRole: "Rol",
  stRowDocument: "Belge",
  stRowVersion: "Sürüm",
  stNotReported: "bildirilmedi",
  stNoDbCheck: "Hazırlık yanıtında veritabanı denetimi yoktu.",
  stOperational: "Çalışıyor",
  stDegraded: "Düşük performans",
  stUnreachable: "Ulaşılamıyor",
  stNeedTitle: "Çalışmak mı istiyorsunuz?",
  stNeedBody:
    "Çalışma alanı — anlaşmalar, belgeler ve mutabakat — bir şirket üyeliğine bağlı, oturum açılmış bir oturum gerektirir.",
  stSignIn: "Giriş yap",
  stFooterApi: "API {url}",
  stFooterSchema: "şema",
  stFooterOpenApi: "OpenAPI {url}",

  shellBreadcrumbAria: "Gezinti yolu",
  shellPrimaryAria: "Ana menü",
  shellHomeAria: "TOUCHE COMMERCE — ana sayfa",
  importStepsAria: "Adımlar",
  cpNotesPlaceholder: "Ödeme koşulları, incoterms, geçmiş…",
  productNamePlaceholder: "Alüminyum külçe A7",

  failGeneric: "İstek tamamlanamadı.",
  failUnreachable: "API'ye ulaşılamıyor. Hizmetin çalıştığını doğrulayıp yeniden deneyin.",
  failUnreachableAt: "{url} adresindeki API'ye ulaşılamıyor. FastAPI'nin çalıştığını doğrulayın.",
  failTimeout: "API {ms} ms içinde yanıt vermedi.",
  failUnexpected: "API beklenmedik bir hata yanıtı döndürdü.",
  failBadJson: "API geçerli JSON olmayan bir gövdeyle yanıt verdi.",
  failOpenApi: "OpenAPI belgesi ayrıştırılamadı.",
  failSessionHttp: "Oturum denetlenirken API HTTP {status} ile yanıt verdi.",
  failProxyDown: "TOUCHE COMMERCE API'sine ulaşılamıyor.",

  shellNoMembership: "Üyelik yok",
  shellStageLabel: "Aşama 6 · Yapay Zekâ Ticaret Direktörü · Salt okunur, insan onaylı",
  navPlannedTip: "{description} — {stage} için planlandı",

  metaDefaultTitle: "TOUCHE COMMERCE — Yönetim Paneli",
  metaDescription: "Bağımsız, premium uluslararası ticaret yönetimi.",

  nfTitle: "Sayfa bulunamadı",
  nfBody: "İstediğiniz sayfa yok veya taşınmış. Hiçbir şey değiştirilmedi.",
  nfBack: "Yönetim paneline dön",
  errTitle: "Bu ekranda bir şeyler ters gitti",
  errBody:
    "Ekran gösterilemedi. Hiçbir şey değiştirilmedi. Yeniden deneyin veya yönetim paneline dönün.",
  errReference: "Referans: {digest}",
  errRetry: "Yeniden dene",
  errHome: "Yönetim paneli",
};
