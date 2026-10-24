"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { ArrowRight, Eye, EyeOff, Loader2 } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { login } from "@/lib/auth/client";
import { safeNextPath } from "@/lib/auth/guard";
import type { ActionResultFailure } from "@/lib/auth/client";
import { useLocale, type Translate } from "@/lib/i18n/locale-provider";

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

interface FieldErrors {
  email?: string;
  password?: string;
}

export function failureMessage(failure: ActionResultFailure, t: Translate): string {
  switch (failure.code) {
    case "RATE_LIMITED":
      return failure.retryAfterSeconds
        ? t("loginRateLimitedSeconds", { seconds: failure.retryAfterSeconds })
        : t("loginRateLimited");
    case "ORIGIN_REJECTED":
    case "CSRF_REJECTED":
      return t("loginRejected");
    case "VALIDATION_ERROR":
      return t("loginCheckFields");
    case "UNAUTHORIZED":
      return t("loginInvalidCredentials");
    default:
      return failure.message;
  }
}

export function LoginForm({ nextPath }: { nextPath: string }) {
  const router = useRouter();
  const { t } = useLocale();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  function validate(): boolean {
    const next: FieldErrors = {};
    const trimmed = email.trim();
    if (!trimmed) next.email = t("loginEmailRequired");
    else if (!EMAIL_PATTERN.test(trimmed)) next.email = t("loginEmailInvalid");
    if (!password) next.password = t("loginPasswordRequired");
    setErrors(next);
    return Object.keys(next).length === 0;
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setFailure(null);
    if (!validate()) return;

    setPending(true);
    const result = await login(email.trim(), password);
    setPending(false);

    if (!result.ok) {
      setFailure(failureMessage(result, t));
      return;
    }

    const needsCompany = result.data.session.company === null;
    router.replace(needsCompany ? "/select-company" : safeNextPath(nextPath));
    router.refresh();
  }

  return (
    <form onSubmit={onSubmit} noValidate className="space-y-5">
      {failure ? (
        <Alert variant="danger" data-testid="login-error">
          {failure}
        </Alert>
      ) : null}

      <div className="space-y-1.5">
        <Label htmlFor="email">{t("loginEmail")}</Label>
        <Input
          id="email"
          name="email"
          type="email"
          autoComplete="username"
          autoFocus
          spellCheck={false}
          placeholder="you@company.example"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          aria-invalid={Boolean(errors.email)}
          aria-describedby={errors.email ? "email-error" : undefined}
          disabled={pending}
        />
        {errors.email ? (
          <p id="email-error" className="text-[11.5px] text-crimson-400">
            {errors.email}
          </p>
        ) : null}
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="password">{t("loginPassword")}</Label>
        <div className="relative">
          <Input
            id="password"
            name="password"
            type={showPassword ? "text" : "password"}
            autoComplete="current-password"
            placeholder="••••••••••••"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            aria-invalid={Boolean(errors.password)}
            aria-describedby={errors.password ? "password-error" : undefined}
            disabled={pending}
            className="pr-11"
          />
          <button
            type="button"
            onClick={() => setShowPassword((visible) => !visible)}
            aria-label={showPassword ? t("loginHidePassword") : t("loginShowPassword")}
            className="absolute inset-y-0 right-0 flex w-10 items-center justify-center text-mist-500 transition-colors hover:text-mist-200"
          >
            {showPassword ? (
              <EyeOff className="size-4" aria-hidden />
            ) : (
              <Eye className="size-4" aria-hidden />
            )}
          </button>
        </div>
        {errors.password ? (
          <p id="password-error" className="text-[11.5px] text-crimson-400">
            {errors.password}
          </p>
        ) : null}
      </div>

      <Button type="submit" className="h-10 w-full" disabled={pending}>
        {pending ? (
          <>
            <Loader2 className="size-4 animate-spin" aria-hidden />
            {t("loginSubmitting")}
          </>
        ) : (
          <>
            {t("loginSubmit")}
            <ArrowRight className="size-4" aria-hidden />
          </>
        )}
      </Button>

      <p className="text-[11px] leading-relaxed text-mist-600">{t("loginSessionNote")}</p>
    </form>
  );
}
