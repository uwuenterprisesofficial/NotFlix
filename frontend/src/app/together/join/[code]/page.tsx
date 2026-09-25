import Link from "next/link";
import { Avatar } from "@/components/together/Avatar";
import { AcceptInvite, JoinAsGuest, RememberInvite } from "@/components/together/TogetherActions";
import { apiOrNull } from "@/lib/api";
import { getT } from "@/lib/i18n/server";
import type { InviteInfo, Me } from "@/lib/types";

export default async function JoinPage({ params }: PageProps<"/together/join/[code]">) {
  const { code } = await params;
  const [{ t }, me, invite] = await Promise.all([
    getT(),
    apiOrNull<Me>("/me"),
    /^[\w-]+$/.test(code) ? apiOrNull<InviteInfo>(`/together/invites/${code}`) : null,
  ]);

  let body: React.ReactNode;
  if (!invite) {
    body = <p className="text-muted">{t("together.inviteGone")}</p>;
  } else {
    const name = invite.inviter.name;
    body = (
      <>
        <div className="flex items-center gap-4">
          <Avatar person={invite.inviter} size={56} />
          <h1 className="text-2xl font-black md:text-3xl">{t("together.joinTitle", { name })}</h1>
        </div>
        <p className="mt-4 text-muted">{t("together.joinInfo")}</p>
        <div className="mt-6">
          {!me ? (
            <>
              <RememberInvite code={code} />
              <p className="mb-4 text-sm">{t("together.signInToJoin", { name })}</p>
              <Link
                href="/login"
                className="inline-block rounded bg-brand px-5 py-2.5 font-semibold hover:bg-brand-dark"
              >
                {t("login.title")}
              </Link>
              <p className="my-6 text-sm text-muted">— {t("together.or")} —</p>
              <div className="rounded-lg bg-surface-raised p-4">
                <h2 className="font-semibold">{t("together.guestTitle")}</h2>
                <p className="mt-1 mb-3 text-sm text-muted">{t("together.guestInfo", { name })}</p>
                <JoinAsGuest code={code} />
              </div>
            </>
          ) : invite.own ? (
            <p>{t("together.ownInvite")}</p>
          ) : invite.connection_id ? (
            <p>
              {t("together.alreadyConnected", { name })}{" "}
              <Link href={`/together/${invite.connection_id}`} className="underline">
                {t("together.open")}
              </Link>
            </p>
          ) : (
            <AcceptInvite code={code} name={name} />
          )}
        </div>
      </>
    );
  }
  return <div className="mx-auto max-w-xl px-4 pt-32 pb-16">{body}</div>;
}
