function [counts, total] = jev_simulation_counts(ledger, phase)
%JEV_SIMULATION_COUNTS Count attempted simulations in a job's shared ledger.
% A containers.Map handle lets an outer error handler retain completed work.
counts = struct('discovery_junction', 0, 'discovery_controller_baseline', 0, ...
    'discovery_controller_perturbation', 0, 'reference_probe', 0, 'sweep', 0, ...
    'own_gain_probe', 0, 'tuning', 0, 'final_verification', 0);
total = 0;
if ~isa(ledger, 'containers.Map'), return; end
if nargin >= 2
    if ~isKey(ledger, phase), ledger(phase) = 0; end
    ledger(phase) = ledger(phase) + 1;
end
names = keys(ledger);
for k = 1:numel(names)
    counts.(names{k}) = ledger(names{k});
    total = total + ledger(names{k});
end
end
