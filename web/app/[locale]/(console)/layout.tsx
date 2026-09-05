import { Header } from "@/components/shell/header";
import { Rail } from "@/components/shell/rail";
import { Tape } from "@/components/tape/tape";
import { LiveBoot } from "@/components/shell/live-boot";
import { ConsoleFrame } from "@/components/shell/console-frame";

export default function ConsoleLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <LiveBoot />
      <Rail />
      <ConsoleFrame>
        <Header />
        <Tape />
        <main id="main" className="mx-auto w-full max-w-[1600px] flex-1 px-3 pb-24 pt-4 sm:px-5 lg:pb-8">
          {children}
        </main>
      </ConsoleFrame>
    </>
  );
}
