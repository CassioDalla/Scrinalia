import { useNavigate } from "@tanstack/react-router";

import { PageHeader } from "@/components/layout/PageHeader";
import { PasswordChangeForm } from "@/components/layout/PasswordChangeForm";
import { SCREENS } from "@/lib/screens";

/**
 * The voluntary password change, on its own route.
 *
 * It used to replace the content area from inside the rail, which meant it had no URL and the
 * browser's Back did not close it. A route gives the screen an address and makes Back the ordinary
 * way out; the forced change (the temporary password printed by the CLI) still stays in the shell,
 * because until it is replaced there is no screen to navigate to.
 *
 * After a successful change the form refetches the account, and this route returns to the inbox:
 * the API keeps this session and ends the others, so the person lands where the session began.
 */
export function PasswordRoute() {
  const navigate = useNavigate();

  return (
    <>
      <PageHeader screen="password" />
      <div className="px-6 py-5">
        <PasswordChangeForm showTitle={false} onDone={() => navigate({ to: SCREENS.inbox.path })} />
      </div>
    </>
  );
}
