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

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

interface FieldErrors {
  email?: string;
  password?: string;
}

export function failureMessage(failure: ActionResultFailure): string {
  switch (failure.code) {
    case "RATE_LIMITED":
      return failure.retryAfterSeconds
        ? `Too many sign-in attempts. Try again in ${failure.retryAfterSeconds} seconds.`
        : "Too many sign-in attempts. Try again later.";
    case "ORIGIN_REJECTED":
    case "CSRF_REJECTED":
      return "The sign-in request was rejected by the server. Reload the page and try again.";
    case "VALIDATION_ERROR":
      return "Check the email address and password, then try again.";
    case "UNREACHABLE":
      return failure.message;
    default:
      return failure.message;
  }
}

export function LoginForm({ nextPath }: { nextPath: string }) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  function validate(): boolean {
    const next: FieldErrors = {};
    const trimmed = email.trim();
    if (!trimmed) next.email = "Enter your work email.";
    else if (!EMAIL_PATTERN.test(trimmed)) next.email = "Enter a valid email address.";
    if (!password) next.password = "Enter your password.";
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
      setFailure(failureMessage(result));
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
        <Label htmlFor="email">Email</Label>
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
        <Label htmlFor="password">Password</Label>
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
            aria-label={showPassword ? "Hide password" : "Show password"}
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
            Signing in…
          </>
        ) : (
          <>
            Sign in
            <ArrowRight className="size-4" aria-hidden />
          </>
        )}
      </Button>

      <p className="text-[11px] leading-relaxed text-mist-600">
        Sessions are held server-side and expire after 30 minutes of inactivity or 12 hours in
        total. Credentials are verified with Argon2id; failed attempts are rate limited.
      </p>
    </form>
  );
}
