import { redirect } from 'next/navigation';
import { AuthError } from 'next-auth';
import { auth, signIn } from '@/lib/auth';
import ThemeToggle from '@/components/ThemeToggle';
import GuestForm from '@/components/GuestForm';

export default async function Login({ searchParams }: { searchParams: Promise<{ error?: string }> }) {
  const session = await auth();
  if (session?.user) redirect('/');
  const { error } = await searchParams;

  return (
    <div className="wrap center">
      <span className="login-toggle">
        <ThemeToggle />
      </span>
      <div className="card login">
        <div className="brand big">Client Intelligence</div>
        <p className="muted">Private, daily competitive intelligence. Sign in to continue.</p>
        {error && (
          <p className="err">
            {error === 'AccessDenied'
              ? 'This Google account is not authorised.'
              : error === 'CredentialsSignin'
                ? 'Wrong login ID or password.'
                : 'Sign-in failed. Please try again.'}
          </p>
        )}

        <GuestForm
          action={async (formData: FormData) => {
            'use server';
            try {
              await signIn('credentials', {
                username: formData.get('username'),
                password: formData.get('password'),
                redirectTo: '/',
              });
            } catch (e) {
              if (e instanceof AuthError) redirect('/login?error=CredentialsSignin');
              throw e;
            }
          }}
        />

        <div className="or">
          <span>or</span>
        </div>
        <form
          action={async () => {
            'use server';
            await signIn('google', { redirectTo: '/' });
          }}
        >
          <button className="btn text" type="submit">
            Team sign-in with Google
          </button>
        </form>
      </div>
    </div>
  );
}
