export function readFence() {
  let epoch = 0, issued = 0, accepted = 0;
  return {
    event() { epoch += 1; },
    start() { return { epoch, sequence: ++issued }; },
    current(ticket: { epoch: number }) { return ticket.epoch === epoch; },
    accept(ticket: { epoch: number; sequence: number }) {
      if (ticket.epoch !== epoch || ticket.sequence < accepted) return false;
      accepted = ticket.sequence;
      return true;
    },
  };
}
