function jev_close_all()
%JEV_CLOSE_ALL  Close every model without leaving one stuck in Fast Restart.
%
%   Closing a model that is still initialised in Fast Restart raises a modal
%   dialog ("Do you want to exit Fast Restart and close the model?").  When a
%   session is driven by an agent nobody can click it, so this helper always
%   disables Fast Restart first.

bds = find_system('SearchDepth', 0, 'Type', 'block_diagram');
for i = 1:numel(bds)
    name = bds{i};
    try, set_param(name, 'FastRestart', 'off'); catch, end
    try, close_system(name, 0); catch, end
end
fprintf('[jev] closed %d model(s)\n', numel(bds));
end
