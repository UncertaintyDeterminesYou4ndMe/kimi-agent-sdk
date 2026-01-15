import { useState } from "react";
import { IconTrash, IconSettings, IconServer } from "@tabler/icons-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { useChatStore, useSettingsStore } from "@/stores";
import { bridge } from "@/services";
import { cn } from "@/lib/utils";

export function ActionMenu({ className }: { className?: string }) {
  const [open, setOpen] = useState(false);
  const { startNewConversation } = useChatStore();
  const { setMCPModalOpen } = useSettingsStore();

  const handleOpenSettings = () => {
    bridge.openSettings();
    setOpen(false);
  };

  const handleOpenMCPServers = () => {
    setMCPModalOpen(true);
    setOpen(false);
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="icon-xs" className={cn("text-muted-foreground", className)}>
          <IconSettings className="size-3.5" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-48 p-1.5 gap-0!" align="end" side="top">
        <button
          onClick={handleOpenMCPServers}
          className="w-full flex items-center gap-2 px-1.5 py-1.5 rounded-md text-xs hover:bg-accent transition-colors text-left cursor-pointer"
        >
          <IconServer className="size-3.5 text-muted-foreground" />
          <span className="flex-1">MCP Servers</span>
        </button>
        <button onClick={handleOpenSettings} className="w-full flex items-center gap-2 px-1.5 py-1.5 rounded-md text-xs hover:bg-accent transition-colors text-left cursor-pointer">
          <IconSettings className="size-3.5 text-muted-foreground" />
          <span className="flex-1">Settings</span>
          <span className="text-[10px] text-muted-foreground">↗</span>
        </button>
      </PopoverContent>
    </Popover>
  );
}
