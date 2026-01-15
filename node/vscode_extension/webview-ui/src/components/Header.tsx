import { useState } from "react";
import { IconPlus, IconChevronDown } from "@tabler/icons-react";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { KimiLogo } from "./KimiLogo";
import { SessionList } from "./SessionList";
import { useChatStore } from "@/stores";
import { ChatStatus } from "./ChatStatus";

export function Header() {
  const [showSessionList, setShowSessionList] = useState(false);
  const { startNewConversation } = useChatStore();

  const handleNewSession = async () => {
    await startNewConversation();
    setShowSessionList(false);
  };

  return (
    <header className="flex items-center justify-between px-3 py-2 border-b border-border shrink-0 @container">
      <div className="flex items-center gap-2">
        <KimiLogo className="size-5" />
        <span className="text-sm font-semibold">Kimi Code</span>
      </div>
      <div className="flex items-center gap-1">
        <ChatStatus />
        <Popover open={showSessionList} onOpenChange={setShowSessionList}>
          <PopoverTrigger asChild>
            <Button variant="ghost" size="xs" className="gap-1 h-6">
              <span className="text-xs @max-[280px]:hidden">History</span>
              <IconChevronDown className="size-3.5" />
            </Button>
          </PopoverTrigger>
          <PopoverContent align="end" className="w-80 p-0">
            <SessionList onClose={() => setShowSessionList(false)} />
          </PopoverContent>
        </Popover>
        <Button variant="ghost" size="icon-xs" onClick={handleNewSession}>
          <IconPlus className="size-3.5" />
        </Button>
      </div>
    </header>
  );
}
