return function(c)
  local s=c.state+1
  if s>1000000 then s=0 end
  local h=c.history
  local n=#h
  local dx=0
  local dy=0
  if n<4 then
    local p=s%4
    if p==1 then dx=1
    elseif p==2 then dy=1
    elseif p==3 then dx=-1
    else dy=-1 end
  else
    local echo=h[1]
    local nxt=h[2]
    local tx=echo.x
    local ty=echo.y
    local reversed=false
    if n>=3 then
      local a=h[n-2]
      local b=h[n-1]
      local d=h[n]
      local x1=b.x-a.x
      local y1=b.y-a.y
      local x2=d.x-b.x
      local y2=d.y-b.y
      if x2==-x1 and y2==-y1 and (x1~=0 or y1~=0) then
        reversed=true
        dx=x1
        dy=y1
        if dx>1 then dx=1 elseif dx<-1 then dx=-1 end
        if dy>1 then dy=1 elseif dy<-1 then dy=-1 end
      end
    end
    if not reversed then
      if c.mx==tx and c.my==ty then
        dx=nxt.x-tx
        dy=nxt.y-ty
        if dx>1 then dx=1 elseif dx<-1 then dx=-1 end
        if dy>1 then dy=1 elseif dy<-1 then dy=-1 end
      else
        local adx=tx-c.mx
        local ady=ty-c.my
        local ax=adx
        if ax<0 then ax=-ax end
        local ay=ady
        if ay<0 then ay=-ay end
        if ax>=ay then
          if adx>0 then dx=1 elseif adx<0 then dx=-1 end
        else
          if ady>0 then dy=1 elseif ady<0 then dy=-1 end
        end
      end
      if s%4==0 then
        local t=dx
        dx=-dy
        dy=t
      end
    end
  end
  return {dx=dx,dy=dy,state=s}
end
