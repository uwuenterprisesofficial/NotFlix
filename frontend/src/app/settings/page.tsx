import type { Metadata } from "next";
import { SettingsForm } from "@/components/SettingsForm";

export const metadata: Metadata = { title: "Settings · NotFlix" };

export default function SettingsPage() {
  return (
    <div className="mx-auto max-w-2xl px-4 pt-24 pb-16">
      <h1 className="text-3xl font-black">Settings</h1>
      <p className="mt-1 text-sm text-muted">Saved in this browser.</p>
      <SettingsForm />
    </div>
  );
}
