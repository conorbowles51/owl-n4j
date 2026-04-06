import React from 'react';
import { Smartphone, Phone, MessageSquare, MapPin, Mail, User, Hash, Shield } from 'lucide-react';

/**
 * Device cards dashboard showing all ingested phone reports.
 */
export default function CellebriteOverview({ caseId, reports }) {
  if (!reports || reports.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center text-light-500 text-sm">
        No phone reports available
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {reports.map((report) => (
          <DeviceCard key={report.report_key} report={report} />
        ))}
      </div>
    </div>
  );
}

function DeviceCard({ report }) {
  const stats = report.stats || {};
  const totalComms = (stats.calls || 0) + (stats.messages || 0) + (stats.emails || 0);

  return (
    <div className="bg-white border border-light-200 rounded-lg shadow-sm hover:shadow-md transition-shadow">
      {/* Header */}
      <div className="p-4 border-b border-light-100 bg-gradient-to-r from-emerald-50 to-white">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 bg-emerald-100 rounded-lg flex items-center justify-center flex-shrink-0">
            <Smartphone className="w-5 h-5 text-emerald-600" />
          </div>
          <div className="min-w-0 flex-1">
            <h3 className="text-sm font-semibold text-owl-blue-900 truncate">
              {report.device_model || 'Unknown Device'}
            </h3>
            {report.phone_owner_name && (
              <div className="flex items-center gap-1 mt-0.5">
                <User className="w-3 h-3 text-light-500" />
                <span className="text-xs text-light-600 truncate">
                  {report.phone_owner_name}
                </span>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Device Info */}
      <div className="p-4 space-y-2">
        {report.phone_numbers && (
          <InfoRow icon={Phone} label="Phone" value={report.phone_numbers} />
        )}
        {report.imei && (
          <InfoRow icon={Hash} label="IMEI" value={report.imei} />
        )}
        {report.extraction_type && (
          <InfoRow icon={Shield} label="Extraction" value={report.extraction_type} />
        )}
        {report.case_number && (
          <InfoRow icon={Hash} label="Case #" value={report.case_number} />
        )}
        {report.examiner && (
          <InfoRow icon={User} label="Examiner" value={report.examiner} />
        )}
      </div>

      {/* Stats */}
      <div className="px-4 pb-4">
        <div className="grid grid-cols-3 gap-2">
          <StatBadge
            icon={User}
            count={stats.contacts || 0}
            label="Contacts"
            color="blue"
          />
          <StatBadge
            icon={Phone}
            count={stats.calls || 0}
            label="Calls"
            color="green"
          />
          <StatBadge
            icon={MessageSquare}
            count={stats.messages || 0}
            label="Messages"
            color="purple"
          />
          <StatBadge
            icon={MapPin}
            count={stats.locations || 0}
            label="Locations"
            color="orange"
          />
          <StatBadge
            icon={Mail}
            count={stats.emails || 0}
            label="Emails"
            color="red"
          />
          <StatBadge
            icon={MessageSquare}
            count={totalComms}
            label="Total Comms"
            color="emerald"
          />
        </div>
      </div>
    </div>
  );
}

function InfoRow({ icon: Icon, label, value }) {
  return (
    <div className="flex items-center gap-2 text-xs">
      <Icon className="w-3 h-3 text-light-400 flex-shrink-0" />
      <span className="text-light-500 w-16 flex-shrink-0">{label}</span>
      <span className="text-owl-blue-900 truncate">{value}</span>
    </div>
  );
}

const colorMap = {
  blue: 'bg-owl-blue-50 text-owl-blue-700',
  green: 'bg-green-50 text-green-700',
  purple: 'bg-purple-50 text-purple-700',
  orange: 'bg-orange-50 text-orange-700',
  red: 'bg-red-50 text-red-700',
  emerald: 'bg-emerald-50 text-emerald-700',
};

function StatBadge({ icon: Icon, count, label, color }) {
  return (
    <div className={`rounded p-2 text-center ${colorMap[color] || colorMap.blue}`}>
      <div className="text-sm font-semibold">{count.toLocaleString()}</div>
      <div className="text-[10px] opacity-75">{label}</div>
    </div>
  );
}
