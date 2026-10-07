return function(c)
  local s=c.state
  if s>7 then s=0 end
  local n=#c.history
  local dx=0
  local dy=0
  if s<4 and n>0 then
    local i=n
    if s==1 and n>1 then i=n-1 elseif s==3 and n>2 then i=n-2 end
    local p=c.history[i]
    if p~=nil then
      if p.x>c.mx then dx=1 elseif p.x<c.mx then dx=-1 end
      if p.y>c.my then dy=1 elseif p.y<c.my then dy=-1 end
    end
  end
  local ns=s+1
  if ns>7 then ns=0 end
  return {dx=dx,dy=dy,state=ns}
end
